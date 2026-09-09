export interface IdentityChipProps {
  /** Level and document type together, e.g. "Primary 1-2 · Student Handout". */
  children: React.ReactNode;
  /** "default" for page 1 mastheads, "small" for running headers. */
  size?: 'default' | 'small';
  style?: React.CSSProperties;
}

export declare function IdentityChip(props: IdentityChipProps): JSX.Element;
