-- Demo data: fictional members and tools, one row per state the flows name.
INSERT INTO member (member_id, subject, display_name, joined_on) VALUES
  ('m1', 'demo-subject-1', 'Demo Member A', '2026-01-10'),
  ('m2', 'demo-subject-2', 'Demo Member B', '2026-02-03');

INSERT INTO tool (tool_id, name, category, status, last_checked_on) VALUES
  ('T-101', 'cordless drill', 'power', 'available', '2026-03-01'),
  ('T-102', 'cordless drill', 'power', 'returned', '2026-02-14'),
  ('T-201', 'step ladder', 'ladder', 'reserved', '2026-02-20'),
  ('T-301', 'hedge shears', 'garden', 'on-loan', '2026-02-11'),
  ('T-302', 'spade', 'garden', 'on-loan', '2026-02-11'),
  ('T-401', 'claw hammer', 'hand', 'on-loan', '2026-01-30');

-- Member B is at the three-loan limit; T-102 waits four days for its check.
INSERT INTO loan (loan_id, tool_id, member_id, handed_over_on, due_on, returned_on, condition_on_return) VALUES
  ('L-1', 'T-102', 'm1', '2026-03-01', '2026-03-08', '2026-03-06', NULL),
  ('L-2', 'T-301', 'm2', '2026-03-05', '2026-03-12', NULL, NULL),
  ('L-3', 'T-302', 'm2', '2026-03-05', '2026-03-12', NULL, NULL),
  ('L-4', 'T-401', 'm2', '2026-03-07', '2026-03-14', NULL, NULL);
