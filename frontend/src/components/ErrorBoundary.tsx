import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import Card from "./Card";
import Button from "./Button";

export interface ErrorBoundaryProps {
  children: ReactNode;
  /** 값이 바뀌면 에러 상태를 자동 해제한다 (라우트 이동 시 복구). */
  resetKey?: unknown;
  /** 대체 UI 대신 직접 렌더링할 내용. */
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 화면이 백지가 되지 않더라도 원인 단서는 콘솔에 남긴다.
    console.error("[ErrorBoundary]", error, "\ncomponentStack:", info.componentStack);
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps) {
    if (this.state.error !== null && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  reset = () => {
    this.setState({ error: null });
  };

  reload = () => {
    window.location.reload();
  };

  render() {
    const { error } = this.state;
    if (error === null) return this.props.children;
    if (this.props.fallback !== undefined) return this.props.fallback;

    return (
      <main className="mx-auto max-w-[720px] p-4 pb-6" role="alert">
        <Card>
          <h2 className="text-base font-semibold">문제가 발생했습니다</h2>
          <p className="mt-2 text-sm text-muted">
            이 화면을 표시하는 중 오류가 났습니다. 다시 시도해도 같은 문제가 반복되면 새로고침해 주세요.
          </p>
          <p className="mt-3 rounded-lg border border-danger/40 bg-danger/15 px-3 py-2 font-mono text-xs break-words text-danger">
            {error.message || String(error)}
          </p>
          <div className="mt-4 flex gap-2">
            <Button variant="secondary" onClick={this.reset} full>
              다시 시도
            </Button>
            <Button variant="ghost" onClick={this.reload} full>
              새로고침
            </Button>
          </div>
        </Card>
      </main>
    );
  }
}
