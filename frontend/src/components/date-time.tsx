import dayjs from "dayjs";
export function DateTime({ value }: { value: string | Date }) { return <time>{dayjs(value).format("YYYY-MM-DD HH:mm")}</time>; }
