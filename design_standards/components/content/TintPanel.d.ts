export interface TintPanelItem {
  /** Small uppercase label, e.g. "Opening Prayer". */
  label: string;
  text: React.ReactNode;
}

export interface TintPanelProps {
  items: TintPanelItem[];
  /** Adds a 2px blue rule on top — use for a panel that must catch the eye. */
  accent?: boolean;
}

export declare function TintPanel(props: TintPanelProps): JSX.Element;
