import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { Button, EmptyState, ErrorState, Skeleton } from "../ui/kit.jsx";

/* 옛 문서 주소를 지금 문서로 데려간다 (S14 · C2).
 *
 * 문서 화면이 둘이었다. 사용자가 도달하는 쪽(`/team-docs`)은 옛 미러를 읽어 제목이 전부
 * 비어 있었고, 두 화면의 저장이 서로 다른 표에 들어가 같은 문서가 주소마다 다른 글이
 * 됐다. 그래서 화면을 `/knowledge` 하나로 합쳤다.
 *
 * **옛 주소를 죽이지는 않는다.** 알림 딥링크, 감사 로그, 사람들이 걸어 둔 북마크에 옛
 * page id 가 그대로 박혀 있어서, 그 주소가 404 가 되면 사용자에게는 「문서가 사라졌다」로
 * 보인다. 서버가 다리(`documents.legacy_page_id`)를 하나 들고 있으므로 여기서 그것을
 * 물어보고 새 주소로 넘긴다.
 *
 * 못 찾으면 **왜 못 찾았는지 말한다.** 조용히 목록으로 보내면 사용자는 자기가 잘못 눌렀다고
 * 생각하고 같은 링크를 다시 누른다. */
export function LegacyDocRedirect() {
  const { pageId } = useParams();
  const found = useQuery({
    queryKey: ["knowledge", "legacy-document", pageId],
    queryFn: () => api("/api/knowledge/documents/by-legacy/" + encodeURIComponent(pageId)),
    enabled: Boolean(pageId),
    retry: false,
  });

  if (found.isLoading) return <Skeleton kind="page" lines={3} />;

  if (found.isError) {
    const status = found.error && found.error.status;
    if (status === 404) {
      return (
        <EmptyState
          title="옛 주소가 가리키는 문서를 찾지 못했습니다."
          help="문서 화면이 하나로 합쳐졌습니다. 옮겨 오지 않았거나 볼 수 있는 권한이 없는 문서입니다."
          action={<Button href="#/knowledge">문서 목록 열기</Button>}
        />
      );
    }
    return <ErrorState error={found.error} onRetry={() => found.refetch()} />;
  }

  /* `replace` 다. 뒤로가기가 이 중간 화면으로 되돌아오면 다시 앞으로 튕겨 나가서
     사용자는 뒤로가기가 고장 났다고 느낀다. */
  return <Navigate to={"/knowledge/" + found.data.id} replace />;
}

export default LegacyDocRedirect;
