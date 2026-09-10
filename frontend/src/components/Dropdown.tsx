import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

export interface DropdownOption {
  value: string;
  label: string;
}

interface Props {
  value: string;
  options: DropdownOption[];
  onChange: (value: string) => void;
  icon?: ReactNode;
  className?: string;
  title?: string;
}

/** Custom-styled dropdown replacing a native <select> - a native select's
 * open menu can't be restyled at all (browser default), which is why the
 * old course/subject pickers looked out of place next to the rest of the
 * app's custom UI. Reuses .select-wrap for the trigger's look (border,
 * hover, chevron via ::after) and the same open/close interaction shape as
 * the existing .user-foot-dropdown pattern.
 *
 * Keyboard/focus behavior mirrors what a native <select> gives for free:
 * Arrow Up/Down and Home/End move between real DOM-focused option buttons,
 * Enter/Space activate via the button's own native behavior, and focus
 * returns to the trigger on close (whether by selecting, Escape, or an
 * outside click) so Tab order continues naturally from the dropdown
 * instead of resetting to the top of the page. */
export function Dropdown({ value, options, onChange, icon, className, title }: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  };

  useEffect(() => {
    if (!open) return;
    const selectedIndex = Math.max(
      options.findIndex((o) => o.value === value),
      0,
    );
    optionRefs.current[selectedIndex]?.focus();

    const onClickOutside = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close(true);
        return;
      }
      const currentIndex = optionRefs.current.findIndex((el) => el === document.activeElement);
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const next = currentIndex < 0 ? 0 : (currentIndex + 1) % options.length;
        optionRefs.current[next]?.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = currentIndex < 0 ? options.length - 1 : (currentIndex - 1 + options.length) % options.length;
        optionRefs.current[prev]?.focus();
      } else if (e.key === 'Home') {
        e.preventDefault();
        optionRefs.current[0]?.focus();
      } else if (e.key === 'End') {
        e.preventDefault();
        optionRefs.current[options.length - 1]?.focus();
      }
    };
    document.addEventListener('mousedown', onClickOutside);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClickOutside);
      document.removeEventListener('keydown', onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const current = options.find((o) => o.value === value);

  return (
    <div className={`select-wrap dropdown${className ? ` ${className}` : ''}`} ref={wrapRef} title={title}>
      {icon && <span className="select-wrap-icon">{icon}</span>}
      <button
        type="button"
        className="dropdown-trigger"
        ref={triggerRef}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {current?.label ?? value}
      </button>
      {open && (
        <ul className="dropdown-menu" role="listbox">
          {options.map((o, i) => (
            <li key={o.value}>
              <button
                type="button"
                role="option"
                aria-selected={o.value === value}
                ref={(el) => {
                  optionRefs.current[i] = el;
                }}
                className={`dropdown-option${o.value === value ? ' active' : ''}`}
                onClick={() => {
                  onChange(o.value);
                  close(true);
                }}
              >
                {o.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
