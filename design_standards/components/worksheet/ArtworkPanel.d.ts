export interface ArtworkPanelProps {
  /** Path to the week's piece of classic religious art. */
  src: string;
  /** Artist, title, year — printed at 8px beneath. */
  credit?: string;
  /** Panel height. 168px is standard; drop it before shrinking type. */
  height?: string;
  /** object-position, for cropping to the figures. */
  position?: string;
}

export declare function ArtworkPanel(props: ArtworkPanelProps): JSX.Element;
