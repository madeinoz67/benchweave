import type { ReactNode } from "react";

import "./data-table.css";

export interface DataColumn<Row> {
  id: string;
  header: string;
  cell(row: Row): ReactNode;
}

export interface DataTableProps<Row> {
  caption: string;
  rows: readonly Row[];
  columns: readonly DataColumn<Row>[];
  rowKey(row: Row): string;
}

export function DataTable<Row>({ caption, rows, columns, rowKey }: DataTableProps<Row>) {
  return (
    <div className="bw-table-wrap">
      <table className="bw-data-table">
        <caption>{caption}</caption>
        <thead><tr>{columns.map((column) => <th key={column.id} scope="col">{column.header}</th>)}</tr></thead>
        <tbody>{rows.map((row) => <tr key={rowKey(row)}>{columns.map((column) => <td key={column.id}>{column.cell(row)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
