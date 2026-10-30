import React from "react";

type Props = React.PropsWithChildren<{
  /** Route-level boundaries pass the pathname so navigating away clears the error. */
  resetKey?: string;
}>;
type State = { failed: boolean; resetKey?: string };

class AppErrorBoundary extends React.Component<Props, State> {
  state: State = { failed: false, resetKey: this.props.resetKey };

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey === state.resetKey ? null : { failed: false, resetKey: props.resetKey };
  }

  componentDidCatch(error: Error): void {
    console.error("The application could not render", error);
  }

  render(): React.ReactNode {
    if (!this.state.failed) return this.props.children;

    const page = (
      <div className="page" role="alert">
        <h1>This page could not load</h1>
        <p>The site may have been updated while this tab was open.</p>
        <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
          Reload page
        </button>
      </div>
    );
    // The root boundary replaces the whole app; route boundaries sit inside the layout.
    return this.props.resetKey === undefined ? <main>{page}</main> : page;
  }
}

export default AppErrorBoundary;
