export interface WritingLinesProps {
  /** One line per answer the activity asks for — never fewer. */
  count: number;
  /** Numbered lines when the activity asks for a set number of items. */
  numbered?: boolean;
  /** Line spacing. 14px for young hands, 12–13px for older. */
  height?: string;
}

export declare function WritingLines(props: WritingLinesProps): JSX.Element;
