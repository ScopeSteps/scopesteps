# Design review, Welcome new starter portal

Synthetic transcript; all names are fictional. Recorded and transcribed by Teams.

[00:00:03] Hannah: Morning. Felix, you've got the screens?

[00:00:06] Felix: I have. Give me one second, I'm sharing the wrong window. That's my kitchen quote. Please don't look at the price of tiles.

[00:00:13] Sophie: Too late. Is that per tile?

[00:00:16] Felix: Per square metre, thankfully. Right, here we go. So I've taken everything from the workshop and turned it into the starter's journey. Before we go through it, Hannah, did legal come back on the open bits?

[00:00:27] Hannah: Some of them. I'll go through as we hit them.

[00:00:30] Felix: Great. So, first screen, signing in. Starters don't have a company account before day one, so they sign in with their personal email address and a one-time code we send them each time. No password to remember.

[00:00:42] Amira: That's what I wanted. The one-time code is our second factor, effectively. And if the offer's withdrawn, the access has to stop the same day.

[00:00:50] Hannah: Agreed. Starters sign in with their personal email and a one-time code, and access ends the day an offer is withdrawn.

[00:00:57] Felix: Then the home screen. This is where the quiz idea ended up. No badges, I listened, but there's a progress bar showing how much they've done before day one.

[00:01:06] Ben: I love that. Can managers see it too?

[00:01:09] Felix: The manager sees the progress on their checklist page, yes. Not the details, just how far along.

[00:01:14] Hannah: Good. Progress bar for the starter, and the manager sees the overall progress but not the details.

[00:01:20] Felix: Then the forms, personal details, emergency contact, bank and tax. Bank and tax go straight to payroll on submit and nothing's kept on our side, as agreed.

[00:01:29] Sophie: And payroll gets told if they change them after submitting?

[00:01:32] Felix: Any change goes straight to payroll the same way.

[00:01:35] Sophie: Perfect.

[00:01:37] Felix: Right to work. They upload the document, HR sees it in a queue, and on day one HR records that they've seen the original. Now, the bit that was open, how long we keep the images.

[00:01:47] Hannah: Legal haven't answered that one yet. Amira's review says delete thirty days after the check, Joel's team's list says keep a copy for audit. They're looking at the Home Office guidance. So that stays open, I'm afraid. Felix, build it so either is possible.

[00:02:02] Amira: As long as nobody quietly picks "keep forever" in the meantime.

[00:02:06] Hannah: Nobody's picking anything until legal answers.

[00:02:09] Felix: Adjustments. This came out of what Joel said last time. There's an optional form where a starter can ask for reasonable adjustments, a different chair, screen settings, working hours, whatever they need.

[00:02:20] Joel: Who sees it?

[00:02:22] Felix: That's the question I wanted answered.

[00:02:24] Hannah: HR sees it. The manager only sees it if the starter agrees to share it. The starter ticks a box to say whether their manager can see it. Nobody else.

[00:02:33] Joel: That's much better than what happens now.

[00:02:36] Felix: Diversity monitoring. Hannah, legal?

[00:02:39] Hannah: Legal said yes, we can collect it, but it has to be optional, every question has to have a "prefer not to say", and it's kept separate from the employee record and only used for anonymous reporting. HR advisers don't see individual answers.

[00:02:53] Amira: Separate store, no link back to the person in the reports. I can live with that.

[00:02:58] Felix: Then the short-notice starters. That was open as well.

[00:03:01] Amira: I've sorted that with Hannah. We're keeping a pool of ten loan laptops. Anyone starting less than ten working days after they accept gets a loan laptop on day one, and their own one follows.

[00:03:12] Hannah: Yes. The portal flags short-notice starters to the service desk so they get a loan laptop.

[00:03:18] Ben: Can I ask about contractors? I've got two starting in October.

[00:03:21] Hannah: I thought about it. Contractors aren't in the first release. Their onboarding is different, they come through procurement. We can look again next year.

[00:03:30] Ben: Okay, I'll do it the old way.

[00:03:32] Sophie: Can I say, completely off topic, did anyone else hear the CEO got a thirty percent rise in April? Apparently it's in the annual report.

[00:03:39] Hannah: Sophie. Not in this meeting, please.

[00:03:41] Sophie: Sorry. Gossip's my cardio.

[00:03:44] Felix: The welcome screen. This is from Joel's original list. Before day one, the starter sees where to go, what time, and who to ask for at reception.

[00:03:52] Joel: That's the question we get most. "Which door do I go in?"

[00:03:56] Felix: And there's a badge photo upload, from the same list. They upload a photo and security prints the badge before they arrive.

[00:04:03] Amira: The photo goes to the badge system and gets deleted from the portal once the badge is printed.

[00:04:08] Felix: Fine by me.

[00:04:10] Amira: Two more from my review, while we're here. The portal has to meet the accessibility standard, WCAG 2.2 at level AA. And sessions time out after fifteen minutes without activity, because people will do this on shared laptops at home.

[00:04:23] Felix: Both fine. The HR platform supports both.

[00:04:27] Hannah: What about if an offer's withdrawn? How long do we keep what they've already put in?

[00:04:32] Joel: We don't have a rule for that today. Paper just goes in the shred bin eventually.

[00:04:37] Hannah: Then that's another one for legal. Let's mark it open. How long we keep a starter's information when their offer is withdrawn.

[00:04:44] Felix: Noted.

[00:04:46] Ben: Has anyone got a spare parking permit, by the way? Mine ran out and the new ones don't come till next month.

[00:04:51] Joel: Speak to facilities. They had some last week.

[00:04:54] Hannah: Right, let me sum up what's new today. One-time code sign-in, access ends when an offer's withdrawn. Progress bar, manager sees progress but not details. Changes to bank details go straight to payroll. Right to work image retention still open, waiting on legal. Adjustments form, HR sees it, manager only with consent. Diversity questions optional, separate, anonymous reporting only. Loan laptops for short-notice starters, flagged by the portal. No contractors in release one. Welcome screen with where and when. Badge photo goes to the badge system and is deleted after printing. WCAG 2.2 AA and a fifteen minute timeout. Retention for withdrawn offers open.

[00:05:36] Felix: Perfect. I'll get going on the build.
