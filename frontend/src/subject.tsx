// §13 친구 열람 — "누구의 데이터를 보고 있는가". null = 나(쓰기 가능), 값 있음 = 친구(읽기 전용).
// 분석·이력·고급 분석 화면이 같은 컴포넌트로 내 것과 친구 것을 그리기 위해 컨텍스트로 내려보낸다.
// 쿼리 키에는 반드시 subject.userId를 넣어 내 캐시와 친구 캐시가 섞이지 않게 한다.
import { createContext, useContext, type ReactNode } from "react";

export interface Subject {
  userId: number;
  username: string;
  displayName: string;
}

const SubjectContext = createContext<Subject | null>(null);

export function SubjectProvider({ subject, children }: { subject: Subject | null; children: ReactNode }) {
  return <SubjectContext.Provider value={subject}>{children}</SubjectContext.Provider>;
}

/** 현재 화면의 대상. readOnly면 편집 UI를 숨긴다. userId는 API의 user_id 파라미터(내 것이면 undefined). */
export function useSubject(): { subject: Subject | null; userId: number | undefined; readOnly: boolean; basePath: string } {
  const subject = useContext(SubjectContext);
  return {
    subject,
    userId: subject?.userId,
    readOnly: subject !== null,
    basePath: subject ? `/u/${encodeURIComponent(subject.username)}` : "",
  };
}
