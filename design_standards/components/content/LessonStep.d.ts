export interface LessonStepProps {
  /** Step number. */
  n: number;
  /** Minutes for this step. */
  minutes: number;
  /** The instruction. Open with a bolded imperative: "Opening.", "Read it." */
  children: React.ReactNode;
  /** A TintPanel holding every text the step speaks aloud. */
  texts?: React.ReactNode;
}

export declare function LessonStep(props: LessonStepProps): JSX.Element;
