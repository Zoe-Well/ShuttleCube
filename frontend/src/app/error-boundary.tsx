import { Component, type ErrorInfo, type ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {};
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error(error, info); }
  render() { return this.state.error ? <div className="card m-8 p-8"><h1>页面暂时无法显示</h1><p>{this.state.error.message}</p><button className="btn" onClick={() => location.reload()}>刷新页面</button></div> : this.props.children; }
}
