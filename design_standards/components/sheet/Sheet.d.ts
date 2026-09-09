export interface SheetProps {
  /** Page content. Give every direct child flex: none; the footer takes margin-top: auto. */
  children: React.ReactNode;
  /** "lesson" tightens the padding for a dense lesson-outline page. */
  variant?: 'default' | 'lesson';
}

export declare function Sheet(props: SheetProps): JSX.Element;
