# Room booking: approved backlog v2

- Version: `00000000-0000-0000-0000-000000000028`, revision 3
- Approved by `00000000-0000-0000-0000-000000000008` at `2026-10-14T09:00:00Z`
- Content hash: `c6e5730c7c95f79c812c588b897b280a5d7c64e6ce47f9127fe3fdc1253e4f8e`
- Based on: `00000000-0000-0000-0000-000000000027`
- Sources: `00000000-0000-0000-0000-000000000001`
- Exported at `2026-10-14T09:00:00Z`

## Epic: Room booking

Id: `00000000-0000-0000-0000-000000000014`

Booking rooms.

### Story: Book a room

Id: `00000000-0000-0000-0000-000000000015`

As a student, I want to book a room.

Only free rooms are offered.

**Acceptance criteria**

1. A student books one slot. _(source: from the sources)_ `00000000-0000-0000-0000-00000000000a`
   - Evidence (supporting): source version `00000000-0000-0000-0000-000000000001`, passage `00000000-0000-0000-0000-000000000002`: “Students book one slot at a time.”
2. Cancelling is allowed up to one hour before. _(human: confirmed by a reviewer)_ `00000000-0000-0000-0000-00000000000b`
   - Confirmed by decision `00000000-0000-0000-0000-00000000001e`
   - Evidence (supporting): source version `00000000-0000-0000-0000-000000000001`, passage `00000000-0000-0000-0000-000000000003`
3. A confirmation is shown. _(proposed: agent suggestion, accepted)_ `00000000-0000-0000-0000-00000000000c`

**Assumptions**

- Rooms have fixed slots.

## Decisions

### Cancellation

- Id: `00000000-0000-0000-0000-00000000001e` (missing decision, answered)
- Question: How late may a user cancel?
- Why it matters: No rule is agreed.
- Answer: Up to one hour before the start.
- Decided by `00000000-0000-0000-0000-000000000008` at `2026-10-14T09:00:00Z`
- Affects: `00000000-0000-0000-0000-000000000015`

## Out of scope

- Excluded: Paying for rooms.
  - Evidence (supporting): source version `00000000-0000-0000-0000-000000000001`, passage `00000000-0000-0000-0000-000000000002`: “Students book one slot at a time.”
