# Community Energy Billing: Project Brief

Prepared by Valley Sun Community Energy Co-operative. Synthetic example; all names and organisations are fictional. Date: 1 October 2026.

## About the co-operative

Valley Sun is a community-owned energy co-operative. Since 2019 it has installed solar panels on the roofs of the village school, the sports hall, two farms and the church hall, with a total capacity of 1.2 megawatts. Members buy shares to fund new installations, and the electricity is sold to the buildings that host the panels and to the grid.

The co-operative has 640 members. Most live within ten miles of the village, and about a third are over 65. Each member holds between one and two hundred shares. Shares cost £50 each, and members receive interest on them once a year.

Since 2024 the co-operative has also sold electricity directly to 85 member households through a local supply scheme. These households pay Valley Sun for the electricity they use, at a tariff that changes with the time of day.

## The problem

Bills for the 85 supply households are produced by a volunteer, Gareth Lewis, using a spreadsheet he built himself. Every month he downloads meter readings from the meter operator's website, pastes them into the spreadsheet, checks them by hand and emails each household a PDF. The process takes him three full days a month. When Gareth was ill last winter, bills went out five weeks late and the co-operative had to borrow money to pay its own suppliers.

Members also complain that the bills are hard to read. They show a single total and no breakdown by time of day, so members cannot tell whether moving their washing to the afternoon has saved them money.

## Goals

- Produce accurate monthly bills without manual copying.
- Make bills easy to understand.
- Take the dependency on one volunteer out of the process.
- Give the board a clear view of money owed to the co-operative.

## In scope

The system imports half-hourly meter readings for every supply household from the meter operator's data feed each night.

On the first working day of each month, the system calculates every household's bill for the previous month by applying the tariff rate for each half hour.

Each bill shows the usage and cost for each tariff period (peak, standard and off-peak), the standing charge and the total, and is emailed to the household as a PDF.

Members can sign in to an online account to see their bills from the last 24 months and download any of them.

Members pay by direct debit, which is collected 14 days after the bill date.

The finance volunteer sees a list of unpaid bills with the amount and how many days each is overdue.

When meter readings are missing for more than three days in a row, the system flags the household for the finance volunteer to check before the bill is sent.

## Out of scope

Share purchases, share interest and the member register stay in the existing share management system. The new system will not handle them.

The co-operative will not offer gas supply.

## Governance

The board of directors approves any change to tariffs. The chair of the board is Ruth Adeyemi. Any decision that changes what members pay must be confirmed by the board before it goes live.

Day-to-day questions about billing go to the finance volunteer.
