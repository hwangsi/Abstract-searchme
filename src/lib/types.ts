export type Conference = {
  id: number;
  title: string;
  location: string;
  tz: string;
  adapter: string;
  status: "parsing" | "ready" | "failed";
  createdAt: string;
  recordCount?: number;
  error?: string | null;
};

export type Hit = {
  id: number;
  person: string;
  affiliation: string;
  role: string;
  is_primary_author: boolean;
  date: string;
  time: string;
  room: string;
  session_code: string;
  session_title: string;
  talk_title: string;
  page: number;
  startsAt: string | null;
  _score: number;
};
