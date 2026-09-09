export interface ThemeLineProps {
  /** The locked one-sentence theme, identical on all twelve pieces. */
  children: React.ReactNode;
  /** That level's fixed Level Question, in small roman type. Omit for Nursery. */
  levelQuestion?: string;
}

export declare function ThemeLine(props: ThemeLineProps): JSX.Element;
