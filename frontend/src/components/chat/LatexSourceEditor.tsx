import React from "react";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { bracketMatching, StreamLanguage } from "@codemirror/language";
import { stex } from "@codemirror/legacy-modes/mode/stex";
import { highlightSelectionMatches, searchKeymap } from "@codemirror/search";
import { Compartment, EditorState } from "@codemirror/state";
import { drawSelection, EditorView, highlightActiveLine, keymap, lineNumbers } from "@codemirror/view";

/** A controlled CodeMirror surface: parent state remains the browser-only draft. */
export const LatexSourceEditor: React.FC<{
  path: string;
  value: string;
  readOnly: boolean;
  onChange: (value: string) => void;
}> = ({ path, value, readOnly, onChange }) => {
  const host = React.useRef<HTMLDivElement>(null);
  const view = React.useRef<EditorView | null>(null);
  const editability = React.useRef(new Compartment());
  const onChangeRef = React.useRef(onChange);
  onChangeRef.current = onChange;

  React.useEffect(() => {
    if (!host.current) return;
    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        drawSelection(),
        highlightActiveLine(),
        history(),
        highlightSelectionMatches(),
        bracketMatching(),
        StreamLanguage.define(stex),
        keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap, indentWithTab]),
        EditorView.contentAttributes.of({
          "aria-label": `Editing ${path}`,
          class: "ph-no-capture",
          "data-ph-no-autocapture": "true",
          "data-ph-no-capture": "true",
        }),
        editability.current.of(EditorView.editable.of(!readOnly)),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) onChangeRef.current(update.state.doc.toString());
        }),
      ],
    });
    view.current = new EditorView({ state, parent: host.current });
    return () => view.current?.destroy();
  // A selected file has a new document; ordinary controlled changes are applied below.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  React.useEffect(() => {
    const current = view.current;
    if (!current || current.state.doc.toString() === value) return;
    current.dispatch({ changes: { from: 0, to: current.state.doc.length, insert: value } });
  }, [value]);

  React.useEffect(() => {
    view.current?.dispatch({
      effects: editability.current.reconfigure(EditorView.editable.of(!readOnly)),
    });
  }, [readOnly]);

  return (
    <div
      className="latex-source-editor ph-no-capture"
      data-ph-no-autocapture="true"
      data-ph-no-capture="true"
      data-testid="latex-source-editor"
      ref={host}
    />
  );
};
