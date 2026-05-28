import type { ButtonHTMLAttributes, HTMLAttributes } from 'react';

export const VARIANT_CHIP_BASE_CLASS = 'inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ring-1 transition';
export const VARIANT_CHIP_ACTIVE_CLASS = 'bg-indigo-50 text-indigo-900 ring-indigo-200';
export const VARIANT_CHIP_INACTIVE_CLASS = 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50';

interface VariantChipCommonProps {
  letter: string;
  dotClassName?: string;
  dotTestId?: string;
  conceptEn?: string;
  active?: boolean;
}

type VariantChipSpanProps = VariantChipCommonProps & HTMLAttributes<HTMLSpanElement> & {
  as?: 'span';
};

type VariantChipButtonProps = VariantChipCommonProps & ButtonHTMLAttributes<HTMLButtonElement> & {
  as: 'button';
};

export type VariantChipProps = VariantChipSpanProps | VariantChipButtonProps;

function variantChipClassName({
  active = false,
  className = '',
}: Pick<VariantChipCommonProps, 'active'> & { className?: string }): string {
  return [
    VARIANT_CHIP_BASE_CLASS,
    active ? VARIANT_CHIP_ACTIVE_CLASS : VARIANT_CHIP_INACTIVE_CLASS,
    className,
  ]
    .filter(Boolean)
    .join(' ');
}

export function VariantChip(props: VariantChipProps) {
  const {
    as = 'span',
    letter,
    dotClassName = 'bg-current opacity-70',
    dotTestId,
    conceptEn,
    active = false,
    className,
    ...rest
  } = props;
  const children = (
    <>
      <span
        data-testid={dotTestId}
        className={`h-1.5 w-1.5 rounded-full ${dotClassName}`}
        aria-hidden={dotTestId ? undefined : true}
      />
      <span>{letter}</span>
      {conceptEn && <span className="sr-only">{conceptEn}</span>}
    </>
  );

  if (as === 'button') {
    const buttonProps = rest as ButtonHTMLAttributes<HTMLButtonElement>;
    return (
      <button
        {...buttonProps}
        type={buttonProps.type ?? 'button'}
        className={variantChipClassName({ active, className })}
      >
        {children}
      </button>
    );
  }

  const spanProps = rest as HTMLAttributes<HTMLSpanElement>;
  return (
    <span
      {...spanProps}
      className={variantChipClassName({ active, className })}
    >
      {children}
    </span>
  );
}
