import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { ReactNode } from "react";

export type ColumnDef<T> = {
  key: keyof T | string;
  header: string;
  render?: (row: T) => ReactNode;
};

export function DataTable<T extends object>({
  title,
  columns,
  rows,
  onRowClick,
  rowClassName,
}: {
  title?: string;
  columns: ColumnDef<T>[];
  rows: T[];
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string;
}) {
  return (
    <Card>
      {title ? (
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
      ) : null}
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                {columns.map((c) => (
                  <TH key={String(c.key)}>{c.header}</TH>
                ))}
              </TR>
            </THead>
            <TBody>
              {rows.map((row, idx) => {
                const rowId = (row as { id?: string }).id ?? idx;

                return (
                <TR
                  key={rowId}
                  data-rowid={String(rowId)}
                  onClick={() => onRowClick?.(row)}
                  className={`${onRowClick ? "cursor-pointer" : ""} ${rowClassName ? rowClassName(row) : ""}`}
                >
                  {columns.map((c) => (
                    <TD key={String(c.key)}>{c.render ? c.render(row) : String((row as Record<string, unknown>)[String(c.key)] ?? "")}</TD>
                  ))}
                </TR>
                );
              })}
            </TBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
