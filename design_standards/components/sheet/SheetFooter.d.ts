export interface SheetFooterProps {
  /** Piece and date. */
  left: string;
  /** "Page n of m". */
  right: string;
  /** ESV, hymn-license and authorship credit. Once per document, not once per page. */
  credit?: string;
}

export declare function SheetFooter(props: SheetFooterProps): JSX.Element;
