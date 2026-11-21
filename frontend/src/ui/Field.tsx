import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { cx } from './cx';

const control =
  'w-full rounded-ui border bg-surface text-ink font-ui text-body placeholder:text-muted/70 ' +
  'transition-colors focus:outline-none focus:border-accent disabled:bg-sunken disabled:text-muted';

const controlState = (invalid?: boolean) => (invalid ? 'border-bad' : 'border-line-strong');

interface FieldProps {
  label: string;
  /** Short help under the label */
  hint?: ReactNode;
  error?: string | null;
  /** Shows "Optional" next to the label */
  optional?: boolean;
  children: (props: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
  className?: string;
}

/**
 * Label + control + hint + error, wired for screen readers.
 * The control is passed as a render function so it gets the right id and aria attributes.
 */
export function Field({ label, hint, error, optional, children, className }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={cx('space-y-1.5', className)}>
      <label htmlFor={id} className="flex items-baseline justify-between gap-2 text-meta font-medium text-ink">
        {label}
        {optional && <span className="font-normal text-muted">Optional</span>}
      </label>
      {hint && (
        <p id={hintId} className="text-meta text-muted">
          {hint}
        </p>
      )}
      {children({ id, describedBy, invalid: !!error })}
      {error && (
        <p id={errorId} className="text-meta text-bad" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean };

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ invalid, className, ...rest }, ref) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cx(control, controlState(invalid), 'h-9 px-3', className)}
      {...rest}
    />
  );
});

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean };

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { invalid, className, rows = 4, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cx(control, controlState(invalid), 'px-3 py-2 leading-relaxed', className)}
      {...rest}
    />
  );
});

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean };

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { invalid, className, children, ...rest },
  ref,
) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cx(control, controlState(invalid), 'h-9 pl-3 pr-8', className)}
      {...rest}
    >
      {children}
    </select>
  );
});

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: ReactNode;
  description?: ReactNode;
}

export function Checkbox({ label, description, className, id: idProp, ...rest }: CheckboxProps) {
  const generated = useId();
  const id = idProp ?? generated;
  return (
    <div className={cx('flex items-start gap-2.5', className)}>
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 rounded-[3px] border-line-strong accent-[rgb(var(--c-accent))]"
        aria-describedby={description ? `${id}-desc` : undefined}
        {...rest}
      />
      <label htmlFor={id} className="text-body text-ink">
        {label}
        {description && (
          <span id={`${id}-desc`} className="mt-0.5 block text-meta text-muted">
            {description}
          </span>
        )}
      </label>
    </div>
  );
}
