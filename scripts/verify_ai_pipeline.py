"""S9 실검증 — **진짜 모델로** 파싱·chunk·임베딩이 도는지 본다.

## 왜 시험만으로 부족한가

`tests/` 의 임베딩은 전부 가짜 Adapter 로 돈다. 실제 모델을 시험 전제로 만들지 않는
이유는 S8 이 실 NFS 를 시험 전제로 만들지 않은 것과 같다 — 465MB 짜리 파일과 8 vCPU 가
필요하고, 그것이 없는 기계에서 전 스위트가 멈추면 안 된다.

그런데 **가짜로는 안 나오는 결함이 있다.** S8 이 마운트가 멀쩡한 상태에서만 나오는
결함 셋을 실 NFS·실 SMB 에서 찾았다. 여기서 같은 종류의 것은 이렇다:

  * ONNX 세션이 요구하는 입력 이름이 export 마다 다르다(`token_type_ids` 가 있기도
    없기도 하다). 안 맞으면 `InvalidArgument` 로 죽는다.
  * 토크나이저를 패딩 없이 쓰면 배치 안의 줄 길이가 달라 세션이 죽는다.
  * 자르기를 안 걸면 512 토큰이 넘는 chunk 에서 모델이 그대로 죽는다.
  * 접두사를 안 붙이면 **오류가 하나도 안 나고** 품질만 조용히 떨어진다.

셋은 죽어서 드러나고 넷째는 안 드러난다. 그래서 넷째를 **수치로** 본다.

## 반례를 함께 돈다 (CLAUDE.md §7)

「검사가 위반을 못 찾았다」와 「검사가 아무것도 안 봤다」는 다르다. 그래서 이 하네스는
통과 사례만 보지 않는다 — 틀린 접두사·정규화 없는 벡터·빈 모델 디렉터리를 함께 넣고
**그것들이 실제로 걸리는지** 확인한다. 반례가 안 걸리면 이 하네스 전체가 무효다.

## 쓰는 법

    python scripts/verify_ai_pipeline.py --model-root <모델 뿌리> [--out report.json]

`--model-root` 아래에 `intfloat__multilingual-e5-small/` 이 있어야 한다.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from app.ai import catalog, chunking, pooling  # noqa: E402
from app.ai.gateway import contract, registry  # noqa: E402
from app.ai.parsing import registry as parsers  # noqa: E402

#: 의미 점검용 문장. 질의 하나와 **맞는 본문 하나 · 상관없는 본문 하나**를 둔다.
#: 맞는 쪽이 더 가깝지 않으면 접두사나 풀링이 틀린 것이다.
QUERY = "사내 보안 정책 문서를 찾습니다"
NEAR = "이 문서는 사내 정보보안 정책과 접근 통제 규정을 설명합니다."
FAR = "점심 메뉴 투표 결과와 다음 회식 일정을 정리했습니다."


class Result:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})
        mark = "OK " if ok else "FAIL"
        print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
        return ok

    @property
    def failed(self) -> list[str]:
        return [c["name"] for c in self.checks if not c["ok"]]


def _settings(model_root: str):
    class _S:
        data_dir = "var"
        ai_enabled = "true"
        ai_model_root = model_root
        ai_embed_model = ""
        ai_embed_batch_size = 32
        ai_embed_threads = 0
        # 🔴 생성은 **끈다.** S9 의 Exit 조건이 「생성 Adapter 비활성 상태에서」다.
        llm_enabled = "false"

    return _S()


def _cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


# ── 시험용 파일 (손으로 만든다) ──────────────────────────────────────────────


def _docx(path: Path) -> None:
    import zipfile

    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paragraphs = "".join(
        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{title}</w:t></w:r></w:p>'
        f"<w:p><w:r><w:t>{body}</w:t></w:r></w:p>"
        for title, body in (
            ("1. 목적", "이 문서는 사내 정보보안 정책의 목적을 설명합니다. " * 8),
            ("2. 범위", "적용 범위는 전 임직원과 협력사 인력입니다. " * 8),
        )
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="{w}"><w:body>{paragraphs}</w:body></w:document>',
        )


def _pptx(path: Path) -> None:
    import zipfile

    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "<p:presentation/>")
        for index, text in enumerate(
            ("접근 통제 원칙을 정리한 슬라이드입니다.", "감사 로그 보관 기간을 정리했습니다."),
            start=1,
        ):
            archive.writestr(
                f"ppt/slides/slide{index}.xml",
                f'<p:sld xmlns:a="{a}" xmlns:p="{p}"><p:cSld><p:spTree>'
                f"<a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:spTree></p:cSld></p:sld>",
            )


def _xlsx(path: Path) -> None:
    import zipfile

    s = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    rows = "".join(
        f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>항목 {i}</t></is></c>'
        f'<c r="B{i}"><v>{i * 100}</v></c></row>'
        for i in range(1, 6)
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{s}" xmlns:r="{r}"><sheets>'
            '<sheet name="예산" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{pkg}">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{s}"><sheetData>{rows}</sheetData></worksheet>',
        )


def _pdf(path: Path) -> None:
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_text = ["Security policy page one.", "Access control page two."]
    contents = []
    for text in pages_text:
        stream = f"BT /F1 18 Tf 72 700 Td ({text}) Tj ET".encode("ascii")
        contents.append(add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)))
    pages_id = len(objects) + len(pages_text) + 1
    page_ids = [
        add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_id, font, content_id)
        )
        for content_id in contents
    ]
    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids)))
    catalog_id = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % index + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets[1:]:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, catalog_id, xref_at
    )
    path.write_bytes(bytes(out))


FIXTURES = {
    "회의록.docx": (_docx, parsers.MIME_DOCX),
    "발표.pptx": (_pptx, parsers.MIME_PPTX),
    "예산.xlsx": (_xlsx, parsers.MIME_XLSX),
    "규격서.pdf": (_pdf, parsers.MIME_PDF),
}


# ── 본체 ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_ai_pipeline")
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--workdir", default="")
    args = parser.parse_args(argv)

    result = Result()
    report: dict = {"model_root": args.model_root}

    # ── 1. Gateway 가 생성 없이 임베딩만 들고 선다 ──────────────────────────
    gateway = registry.build_gateway(_settings(args.model_root), env={})
    caps = gateway.capabilities()
    report["capabilities"] = caps.as_dict()
    result.add(
        "생성 Adapter 가 비활성이다 (S9 Exit 의 전제)",
        not caps.generate.available,
        f"status={caps.generate.status}",
    )
    if not result.add(
        "임베딩을 쓸 수 있다", caps.embed.available, f"status={caps.embed.status}"
    ):
        return _finish(result, report, args.out)
    report["model"] = caps.embed.model

    # ── 2. 반례: 빈 모델 디렉터리는 거절한다 ────────────────────────────────
    empty = registry.build_gateway(_settings(str(Path(args.model_root) / "없음")), env={})
    result.add(
        "반례 — 모델이 없는 뿌리는 거절한다",
        not empty.capabilities().embed.available,
        f"status={empty.capabilities().embed.status}",
    )

    # ── 3. 진짜 모델로 벡터를 만든다 ────────────────────────────────────────
    started = time.monotonic()
    passages = gateway.embed([NEAR, FAR], kind=catalog.KIND_PASSAGE)
    queries = gateway.embed([QUERY], kind=catalog.KIND_QUERY)
    report["first_call_seconds"] = round(time.monotonic() - started, 2)
    if not result.add("임베딩 호출이 성공했다", passages.ok and queries.ok,
                      f"status={passages.status}/{queries.status}"):
        return _finish(result, report, args.out)

    result.add(
        f"차원이 {catalog.VECTOR_DIM} 이다",
        all(len(v) == catalog.VECTOR_DIM for v in passages.vectors + queries.vectors),
    )
    result.add(
        "모든 벡터가 길이 1 이다",
        all(pooling.is_unit_length(v) for v in passages.vectors + queries.vectors),
    )

    # ── 4. 반례: 정규화를 뺀 벡터는 검사가 잡는다 ──────────────────────────
    result.add(
        "반례 — 정규화 안 된 벡터는 길이 검사가 잡는다",
        not pooling.is_unit_length([v * 3.0 for v in passages.vectors[0]]),
    )

    # ── 5. 같은 글은 같은 벡터다 ────────────────────────────────────────────
    twice = gateway.embed([NEAR], kind=catalog.KIND_PASSAGE)
    same = max(abs(a - b) for a, b in zip(twice.vectors[0], passages.vectors[0]))
    result.add("같은 글은 같은 벡터다", same < 1e-5, f"최대 차이 {same:.2e}")

    # ── 6. 의미가 맞는 쪽이 더 가깝다 ───────────────────────────────────────
    near_score = _cosine(queries.vectors[0], passages.vectors[0])
    far_score = _cosine(queries.vectors[0], passages.vectors[1])
    report["similarity"] = {"near": round(near_score, 4), "far": round(far_score, 4)}
    result.add(
        "맞는 본문이 상관없는 본문보다 가깝다",
        near_score > far_score,
        f"near={near_score:.4f} far={far_score:.4f}",
    )

    # ── 7. 접두사가 실제로 벡터를 바꾼다 ────────────────────────────────────
    # 안 붙여도 오류가 하나도 안 나므로, **붙었다는 사실을 수치로** 본다.
    as_passage = gateway.embed([QUERY], kind=catalog.KIND_PASSAGE)
    prefix_gap = 1.0 - _cosine(queries.vectors[0], as_passage.vectors[0])
    report["prefix_gap"] = round(prefix_gap, 6)
    result.add(
        "query 접두사와 passage 접두사가 다른 벡터를 만든다",
        prefix_gap > 1e-4,
        f"코사인 거리 {prefix_gap:.6f}",
    )

    # ── 8. 512 토큰을 넘는 글도 죽지 않는다 ────────────────────────────────
    long_text = "보안 정책 문장입니다. " * 400
    long_result = gateway.embed([long_text], kind=catalog.KIND_PASSAGE)
    result.add(
        "상한을 넘는 글에서도 죽지 않는다(자르기가 걸려 있다)",
        long_result.ok and len(long_result.vectors[0]) == catalog.VECTOR_DIM,
        f"status={long_result.status}",
    )

    # ── 9. 길이가 다른 글을 한 배치로 태운다(패딩) ─────────────────────────
    mixed = gateway.embed(["짧다.", "조금 더 긴 문장입니다. " * 30, "중간 길이 문장입니다."],
                          kind=catalog.KIND_PASSAGE)
    result.add(
        "길이가 제각각인 배치가 한 번에 돈다(패딩이 걸려 있다)",
        mixed.ok and len(mixed.vectors) == 3,
        f"status={mixed.status}",
    )

    # ── 10. 진짜 파일 → 파싱 → chunk → 임베딩 ──────────────────────────────
    workdir = Path(args.workdir or ".") / "s9_fixtures"
    workdir.mkdir(parents=True, exist_ok=True)
    per_file = {}
    all_chunks: list[chunking.Chunk] = []
    for name, (make, mime) in FIXTURES.items():
        path = workdir / name
        make(path)
        parsed = parsers.parse_file(path, mime_type=mime)
        chunks = chunking.chunk_units(parsed.units, merge_anchors=False)
        per_file[name] = {
            "status": parsed.status,
            "units": len(parsed.units),
            "chunks": len(chunks),
            "anchors": sorted({u.anchor_kind for u in parsed.units}),
            "sample_anchor": parsed.units[0].anchor_ref if parsed.units else "",
        }
        all_chunks.extend(chunks)
    report["files"] = per_file
    result.add(
        "네 형식 모두 글과 앵커가 나온다",
        all(v["status"] == "ok" and v["chunks"] > 0 for v in per_file.values()),
        ", ".join(f"{k}={v['chunks']}" for k, v in per_file.items()),
    )
    result.add(
        "형식마다 자기 앵커를 쓴다",
        {tuple(v["anchors"]) for v in per_file.values()}
        == {("section",), ("slide",), ("sheet",), ("page",)},
        str({k: v["anchors"] for k, v in per_file.items()}),
    )

    chunk_result = gateway.embed([c.text for c in all_chunks], kind=catalog.KIND_PASSAGE)
    result.add(
        "그 chunk 전부가 벡터가 된다",
        chunk_result.ok and len(chunk_result.vectors) == len(all_chunks),
        f"chunk {len(all_chunks)}건",
    )

    # ── 11. 처리량과 메모리 ─────────────────────────────────────────────────
    corpus = [f"{i}번 보안 정책 문단입니다. " * 12 for i in range(256)]
    started = time.monotonic()
    bulk = gateway.embed(corpus, kind=catalog.KIND_PASSAGE)
    elapsed = time.monotonic() - started
    latencies = []
    for _ in range(20):
        tick = time.monotonic()
        gateway.embed([QUERY], kind=catalog.KIND_QUERY)
        latencies.append((time.monotonic() - tick) * 1000)
    report["throughput"] = {
        "docs": len(corpus),
        "seconds": round(elapsed, 2),
        "docs_per_sec": round(len(corpus) / elapsed, 1) if elapsed else None,
    }
    report["query_latency_ms"] = {
        "n": len(latencies),
        "p50": round(statistics.median(latencies), 2),
        "max": round(max(latencies), 2),
    }
    report["max_rss_mb"] = _max_rss_mb()
    result.add("대량 임베딩이 성공했다", bulk.ok, f"{report['throughput']}")
    # 값이 전 표본에서 같으면 측정이 아니라 상수를 읽고 있는 것이다(D-213).
    result.add(
        "질의 지연이 상수가 아니다(진짜로 재고 있다)",
        len(set(round(v, 1) for v in latencies)) > 1,
        f"p50={report['query_latency_ms']['p50']}ms",
    )

    return _finish(result, report, args.out)


def _max_rss_mb():
    try:
        import resource

        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:  # noqa: BLE001 - Windows 에는 없다
        return None


def _finish(result: Result, report: dict, out: str) -> int:
    report["checks"] = result.checks
    report["failed"] = result.failed
    report["passed"] = len(result.checks) - len(result.failed)
    if out:
        Path(out).write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    print("")
    if result.failed:
        print(f"AI_PIPELINE_VERIFY_FAILED ({len(result.failed)}건): {', '.join(result.failed)}")
        return 1
    print(f"AI_PIPELINE_VERIFY_OK (검사 {len(result.checks)}건 전부 통과)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
