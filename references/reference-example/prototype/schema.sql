-- Written from entities/ (member@1, tool@1, loan@2). Rebuilt on every start.
CREATE TABLE member (
  member_id TEXT PRIMARY KEY,
  subject TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  joined_on TEXT NOT NULL
);

CREATE TABLE tool (
  tool_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN ('power', 'hand', 'garden', 'ladder')),
  status TEXT NOT NULL CHECK (status IN ('available', 'reserved', 'on-loan', 'returned', 'in-repair', 'retired')),
  last_checked_on TEXT
);

CREATE TABLE loan (
  loan_id TEXT PRIMARY KEY,
  tool_id TEXT NOT NULL REFERENCES tool (tool_id),
  member_id TEXT NOT NULL REFERENCES member (member_id),
  handed_over_on TEXT NOT NULL,
  due_on TEXT NOT NULL,
  returned_on TEXT,
  condition_on_return TEXT CHECK (condition_on_return IN ('good', 'worn', 'broken'))
);
