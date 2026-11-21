import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from 'lucide-react';
import { cx } from './cx';
import { Button } from './Button';

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Cell content */
  render: (row: T) => ReactNode;
  /** Value to sort by; the column is sortable when this is set */
  sortValue?: (row: T) => string | number | null | undefined;
  align?: 'left' | 'right';
  /** Tailwind width class, e.g. "w-32" */
  width?: string;
  /** Hidden below this breakpoint to keep narrow screens readable */
  hideBelow?: 'sm' | 'md' | 'lg';
  /** Numbers and ids: monospace with aligned digits */
  numeric?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Makes the whole row a link (keyboard: Enter on the focused row) */
  rowHref?: (row: T) => string | undefined;
  loading?: boolean;
  /** Shown when there are no rows and nothing is loading */
  empty?: ReactNode;
  /** Initial sort */
  defaultSort?: { key: string; dir: 'asc' | 'desc' };
  caption?: string;
  /** Page the rows (after sorting) with this many per page */
  pageSize?: number;
  /** Changing this (e.g. a filter or search term) goes back to the first page */
  pageResetKey?: string;
}

const hide: Record<NonNullable<Column<unknown>['hideBelow']>, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  rowHref,
  loading,
  empty,
  defaultSort,
  caption,
  pageSize,
  pageResetKey,
}: DataTableProps<T>) {
  const navigate = useNavigate();
  const [sort, setSort] = useState(defaultSort);
  const [page, setPage] = useState(0);

  useEffect(() => setPage(0), [pageResetKey, sort]);

  const sorted = useMemo(() => {
    const col = sort && columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const get = col.sortValue;
    const dir = sort!.dir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = get(a);
      const vb = get(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1; // empty values last either way
      if (vb == null) return -1;
      return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
    });
  }, [rows, columns, sort]);

  // Stay on a page that still exists when rows go away
  const lastPage = pageSize ? Math.max(0, Math.ceil(sorted.length / pageSize) - 1) : 0;
  const currentPage = Math.min(page, lastPage);
  const shown = pageSize ? sorted.slice(currentPage * pageSize, (currentPage + 1) * pageSize) : sorted;

  const toggleSort = (key: string) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }));

  const showEmpty = !loading && rows.length === 0;

  return (
    <div>
      <div className="relative overflow-x-auto border-y border-line">
        <table className="w-full border-collapse text-left text-body">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr className="border-b border-line bg-sunken/60">
              {columns.map((c) => {
                const active = sort?.key === c.key;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                    className={cx(
                      'h-9 px-3 text-meta font-medium text-muted',
                      c.align === 'right' && 'text-right',
                      c.width,
                      c.hideBelow && hide[c.hideBelow],
                    )}
                  >
                    {c.sortValue ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(c.key)}
                        className={cx('inline-flex items-center gap-1 hover:text-ink', active && 'text-ink')}
                      >
                        {c.header}
                        {active &&
                          (sort!.dir === 'asc' ? (
                            <ArrowUp className="h-3 w-3" aria-hidden />
                          ) : (
                            <ArrowDown className="h-3 w-3" aria-hidden />
                          ))}
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading &&
              rows.length === 0 &&
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={`loading-${i}`} className="border-b border-line last:border-0" aria-hidden>
                  {columns.map((c) => (
                    <td key={c.key} className={cx('h-12 px-3', c.hideBelow && hide[c.hideBelow])}>
                      <span className="block h-3 w-3/4 animate-pulse rounded-sm bg-sunken" />
                    </td>
                  ))}
                </tr>
              ))}
            {shown.map((row) => {
              const href = rowHref?.(row);
              return (
                <tr
                  key={rowKey(row)}
                  className={cx(
                    'border-b border-line bg-surface last:border-0',
                    href && 'cursor-pointer hover:bg-sunken/70 focus-within:bg-sunken/70',
                  )}
                  onClick={
                    href
                      ? (e) => {
                          // Let real links and buttons inside the row do their own thing
                          if ((e.target as HTMLElement).closest('a,button,input,select,label')) return;
                          navigate(href);
                        }
                      : undefined
                  }
                  onKeyDown={
                    href ? (e) => e.key === 'Enter' && e.currentTarget === e.target && navigate(href) : undefined
                  }
                  tabIndex={href ? 0 : undefined}
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={cx(
                        'h-12 px-3 align-middle',
                        c.align === 'right' && 'text-right',
                        c.numeric && 'font-mono text-meta tabular',
                        c.hideBelow && hide[c.hideBelow],
                      )}
                    >
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {showEmpty && (
        <div className="bg-surface p-4">{empty ?? <p className="text-body text-muted">Nothing here.</p>}</div>
      )}
      {pageSize && <Pagination page={currentPage} pageSize={pageSize} total={sorted.length} onPage={setPage} />}
    </div>
  );
}

/** "21–40 of 135" with previous/next. Server or client paging, the caller owns the page number. */
export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  if (total <= pageSize) return null;
  const first = page * pageSize + 1;
  const last = Math.min(total, (page + 1) * pageSize);
  return (
    <nav aria-label="Pages" className="mt-3 flex items-center justify-between text-meta text-muted">
      <span className="tabular">
        {first}–{last} of {total}
      </span>
      <div className="flex gap-1">
        <Button
          size="sm"
          variant="ghost"
          disabled={page === 0}
          onClick={() => onPage(page - 1)}
          icon={<ChevronLeft className="h-4 w-4" aria-hidden />}
        >
          Previous
        </Button>
        <Button size="sm" variant="ghost" disabled={last >= total} onClick={() => onPage(page + 1)}>
          Next
          <ChevronRight className="h-4 w-4" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
