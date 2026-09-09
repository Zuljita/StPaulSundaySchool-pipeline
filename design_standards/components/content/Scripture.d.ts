export interface ScriptureVerse {
  /** Verse number, printed as a red superscript. */
  n: number | string;
  /** The verse text, verbatim ESV. */
  text: string;
}

export interface ScriptureProps {
  verses: ScriptureVerse[];
  /** Two columns everywhere except the narrowest rails. */
  columns?: number;
  /** A --size-scripture* token. Never below 12px. */
  size?: string;
}

export declare function Scripture(props: ScriptureProps): JSX.Element;
