export interface MastheadProps {
  /** Path to the church logo. Omit only if the mark is genuinely unavailable. */
  logoSrc?: string;
  /** Level and document type, passed through to IdentityChip. */
  chip: string;
  /** The Gospel's title for the week — the same h1 on all twelve pieces. */
  title: string;
  date: string;
  /** Both occasions when both apply. */
  occasion: string;
  reference: string;
  /** Season name printed beside the marker, e.g. "Season of Trinity". */
  season: string;
  /** One of the --season-* tokens. */
  seasonColor?: string;
}

export declare function Masthead(props: MastheadProps): JSX.Element;
