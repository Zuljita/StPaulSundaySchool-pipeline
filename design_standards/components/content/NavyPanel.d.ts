export interface NavyPanelProps {
  /** Usually "Memory Work". */
  label: string;
  /** The verse or sentence, set in the display face. */
  children: React.ReactNode;
  /** Reference line, e.g. "Book 0:0". */
  credit?: string;
}

export declare function NavyPanel(props: NavyPanelProps): JSX.Element;
