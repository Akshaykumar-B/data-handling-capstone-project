import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export type Column<T> = {
  header: string;
  align?: "left" | "right";
  render: (row: T) => React.ReactNode;
};

export function DataTable<T>({ columns, rows, getKey }: { columns: Column<T>[]; rows: T[]; getKey: (row: T, index: number) => string }) {
  return (
    <div className="overflow-x-auto rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((column) => (
              <TableHead key={column.header} className={column.align === "right" ? "text-right" : undefined}>
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={getKey(row, index)}>
              {columns.map((column) => (
                <TableCell key={column.header} className={column.align === "right" ? "text-right font-mono tabular-nums" : undefined}>
                  {column.render(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
