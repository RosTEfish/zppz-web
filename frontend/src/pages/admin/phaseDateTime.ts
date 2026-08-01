import dayjs, { type Dayjs } from "dayjs";
import timezone from "dayjs/plugin/timezone";
import utc from "dayjs/plugin/utc";

dayjs.extend(utc);
dayjs.extend(timezone);

export const BUSINESS_TIMEZONE = "Asia/Shanghai";

export function toBusinessTime(value?: string | null): Dayjs | null {
  return value ? dayjs.utc(value).tz(BUSINESS_TIMEZONE) : null;
}

export function toUtcIso(value: Dayjs | null): string {
  return value?.isValid() ? value.utc().toISOString() : "";
}
