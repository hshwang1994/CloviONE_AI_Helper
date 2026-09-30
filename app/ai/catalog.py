"""임베딩 모델 카탈로그 — **모델 이름이 제품 안에 적히는 유일한 자리**.

## 왜 여기만 예외인가

D-201 은 「모델명은 어디에도 하드코딩하지 않는다」고 적었다. 그 규칙이 겨눈 것은
`app/llm/provider.py` 의 `DEFAULT_MODEL = "sonnet"` 처럼 **생성 모델 이름이 호출부 옆에
박혀 있는 것**이다. 생성 모델은 구독·약관·가격이 정하는 운영 선택이라 설정에서 온다.

임베딩 모델은 성격이 다르다. **차원이 DB 컬럼이고**(`vector(384)`), 접두사와 풀링이
벡터 값 자체를 바꾼다. 그래서 운영자가 아무 이름이나 넣을 수 있는 자리가 아니라
**제품이 아는 목록에서 고르는 자리**다 — 목록에 없는 이름은 거절한다. D-211 이 실측으로
고른 것이 `intfloat/multilingual-e5-small` 하나이고, 지금 목록은 그 하나다.

`scripts/check_no_model_names.py` 는 이 파일을 **이름을 적어** 면제한다(D-213 3번).

## `EMBEDDING_VERSION` 을 왜 따로 두는가

같은 모델이어도 접두사(`query: `/`passage: `)나 풀링·정규화를 바꾸면 **어제 만든 벡터와
오늘 만든 벡터를 같은 공간에서 비교할 수 없다.** 모델 이름만 기록하면 그 사고가
「검색 결과가 좀 이상하다」로만 보인다. 그래서 벡터를 만드는 방식이 바뀌면 이 값을 올리고,
색인은 `embedding_model` 과 `embedding_version` 이 둘 다 같을 때만 최신으로 본다.

`PARSER_VERSION` 도 같은 이유다 — 파서를 고치면 같은 파일에서 다른 글이 나온다.
"""

from __future__ import annotations

from dataclasses import dataclass

#: 파서 계약 판. 파싱 결과(텍스트·앵커)가 달라지면 올린다 → 그 판으로 만든 chunk 는 낡는다.
PARSER_VERSION = "1"

#: 임베딩 **방식** 판. 접두사·풀링·정규화·자르기가 달라지면 올린다.
EMBEDDING_VERSION = "1"

#: DB 의 `document_chunks.embedding` 이 이 차원으로 굳어 있다. 다른 차원의 모델로 바꾸는
#: 것은 설정 한 줄이 아니라 **마이그레이션 + 전량 재색인**이다 (D-211 상향 경로).
VECTOR_DIM = 384

#: 전문검색 설정 이름. **인덱스와 질의가 같은 값을 써야 한다** — 다르면 색인은 A 로
#: 토큰을 만들고 질의는 B 로 만들어서, 오류 하나 없이 결과만 조용히 비뜨거나 인덱스를
#: 못 탄다. `simple` 인 이유는 PG 에 한국어 stemmer 가 없기 때문이고(그래서 FTS 는
#: 어절 정확일치만 한다), 그 한계가 곧 D-209 가 후보 생성을 트라이그램에 맡긴 이유다.
FTS_CONFIG = "simple"


@dataclass(frozen=True)
class ModelFile:
    """받을 파일 하나. 크기와 sha256 은 고정한 revision 에서 잰 값이다."""

    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelSource:
    """설치가 모델을 받을 곳(계획 3.16, D-522).

    **revision 을 커밋 해시로 고정한다.** `main` 을 받으면 모델 저장소가 파일을 바꾼 날 같은 설치 명령이 다른 벡터를 만드는
    모델을 깐다. 그러면 어제 만든 색인과 오늘 만든 질의 벡터가 다른 공간에 선다(EMBEDDING_VERSION 이 막으려는 사고).
    파일마다 sha256 을 적어 두고 받은 파일이 그 값과 맞아야만 쓴다. 이 값은 모델 저장소의 LFS 해시와 직접 계산한 값이
    같은지 확인해 적었다.

    받는 것은 설치 스크립트다. 제품(웹, 워커)은 모델 호스트에 나가지 않고, 바깥 허용 목록에도 그 호스트가 없다.
    """

    base_url: str
    revision: str
    files: tuple[ModelFile, ...]

    def url_for(self, item: ModelFile) -> str:
        return f"{self.base_url}/resolve/{self.revision}/{item.path}"


@dataclass(frozen=True)
class EmbeddingModel:
    """임베딩 모델 하나가 무엇인지의 전부."""

    #: HuggingFace 저장소 id 그대로. 모델 디렉터리 이름은 `/` 를 `__` 로 바꾼 것이다.
    model_id: str
    dim: int
    #: e5 계열은 질의와 본문에 서로 다른 접두사를 요구한다. 안 붙이면 품질이 눈에 띄게
    #: 떨어지는데 **오류는 하나도 안 난다** — 그래서 계약에 적어 둔다.
    query_prefix: str
    passage_prefix: str
    #: 토크나이저가 자르는 자리. 모델의 `max_position_embeddings` 와 같아야 한다.
    max_tokens: int
    #: 모델 디렉터리에 반드시 있어야 하는 파일. Stage 12 와 `ai_cli status` 가 이것을 본다.
    required_files: tuple[str, ...] = ("onnx/model.onnx", "tokenizer.json", "config.json")
    #: 설치가 받을 곳(`--download-model`). 없으면 모델 파일을 사람이 넣어야 한다.
    source: ModelSource | None = None

    @property
    def dir_name(self) -> str:
        """`intfloat/multilingual-e5-small` → `intfloat__multilingual-e5-small`.

        `/` 를 그대로 두면 모델 디렉터리 밑에 또 디렉터리가 생기고, 그 모양이 곧
        경로 조립 실수의 자리가 된다. S1 벤치가 쓴 이름과 같은 규칙이다.
        """
        return self.model_id.replace("/", "__")

    def prefix_for(self, kind: str) -> str:
        return self.query_prefix if kind == KIND_QUERY else self.passage_prefix


#: 임베딩 대상의 두 종류. 질의와 본문은 **다른 접두사**를 쓴다.
KIND_QUERY = "query"
KIND_PASSAGE = "passage"
KINDS = (KIND_QUERY, KIND_PASSAGE)

E5_SMALL = EmbeddingModel(
    model_id="intfloat/multilingual-e5-small",
    dim=VECTOR_DIM,
    query_prefix="query: ",
    passage_prefix="passage: ",
    max_tokens=512,
    source=ModelSource(
        base_url="https://huggingface.co/intfloat/multilingual-e5-small",
        revision="614241f622f53c4eeff9890bdc4f31cfecc418b3",
        files=(
            ModelFile("onnx/model.onnx", 470268510,
                      "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665"),
            ModelFile("tokenizer.json", 17082730,
                      "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"),
            ModelFile("config.json", 655,
                      "69137736cab8b8903a07fe8afaafdda25aac55415a12a55d1bffa9f581abf959"),
        ),
    ),
)

#: 제품이 아는 임베딩 모델 전부. 설정은 여기 있는 id 만 받는다.
EMBEDDING_MODELS: dict[str, EmbeddingModel] = {E5_SMALL.model_id: E5_SMALL}

#: 설정이 비었을 때 고르는 것. D-211 의 결정이다.
DEFAULT_EMBEDDING_MODEL_ID = E5_SMALL.model_id


def embedding_model(model_id: str | None) -> EmbeddingModel | None:
    """id → 모델. 모르는 이름이면 None 이다 — 조용히 기본값으로 떨어뜨리지 않는다.

    떨어뜨리면 「모델을 바꿨는데 왜 그대로지」가 되고, 그때 이미 만들어진 벡터는
    바꾼 줄 알았던 모델의 것이 아니다.
    """
    if not model_id:
        return EMBEDDING_MODELS[DEFAULT_EMBEDDING_MODEL_ID]
    return EMBEDDING_MODELS.get(model_id.strip())
