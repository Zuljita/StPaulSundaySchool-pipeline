export interface SectionLabelProps {
  children: React.ReactNode;
  /** "onSolid" inside a navy panel; "law" for the red Law marker. */
  tone?: 'blue' | 'onSolid' | 'law';
  /** "small" for sub-labels inside tint panels. */
  size?: 'default' | 'small';
  style?: React.CSSProperties;
}

export declare function SectionLabel(props: SectionLabelProps): JSX.Element;
