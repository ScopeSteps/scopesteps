# Follow-up meeting, Fieldwork job scheduling

Synthetic transcript; all names are fictional. Recorded and transcribed by Teams.

[00:00:03] Rachel: Morning all. Marcus, thanks for joining, I wanted finance in the room for this one. Has everyone got the pricing Lucy sent round?

[00:00:15] Tom: I've got it, I just haven't read it. I've had a week. Two vans off the road and the Bramley flood.

[00:00:26] Kemi: The Bramley flood was a fun one. I was in water up to my knees at half four on Sunday.

[00:00:37] Rachel: I saw the photos. Thank you all for that, honestly.

[00:00:44] Marcus: I've got it open. That's partly why I'm here, to be honest.

[00:00:51] Dev: Sorry, I'm a bit slow today, the baby was up from two till five. I've had three coffees and I still can't feel my face.

[00:01:04] Kemi: Ah, that stage. It does get better. Around year eighteen.

[00:01:11] Dev: Don't tell me that. I was told six weeks. Then I was told three months.

[00:01:20] Tom: Mine's twenty-four and still rings me at two in the morning for a lift home.

[00:01:29] Marcus: Is that a recommendation or a warning?

[00:01:34] Tom: Bit of both.

[00:01:38] Rachel: Ha. Okay. Before the money, has anyone sorted the Christmas do? Because I've been asked three times this week.

[00:01:48] Tom: The Railway's booked for the twelfth. Twenty five a head, two courses. I'll send the menu round, you have to pick by Friday or you get the fish.

[00:02:02] Kemi: What's the veggie option?

[00:02:06] Tom: Mushroom something. Wellington, I think.

[00:02:10] Kemi: Put me down for that. The fish last year was grey.

[00:02:17] Rachel: I'll pretend I didn't hear that, I organised last year.

[00:02:24] Rachel: Lovely. Right. Lucy, do you want to take us through the offline price?

[00:02:32] Lucy: Before I do, a quick recap for Marcus, since he wasn't at the workshop. At the workshop Rachel decided technicians should be able to see their day without signal in the first release, because about one job in five in the North is somewhere with no signal. Completing a job without signal stays in phase two. That decision wasn't in the statement of work, so I promised to price it. That's what this is.

[00:03:05] Marcus: Thanks, that's helpful. I'd only seen the email.

[00:03:11] Lucy: Sure. So, seeing the day's jobs without signal, read only, downloaded at the start of the day, comes to thirty eight thousand pounds on top of the current statement of work. That includes the testing in the low-signal areas Kemi mentioned. Completing jobs offline is still phase two and isn't in that number.

[00:03:35] Marcus: Can you break that down for me? What's actually in the thirty eight?

[00:03:43] Lucy: Roughly, about eighteen for the build itself, the download and the local storage on the phone, about twelve for testing, because we have to physically go to the dead spots with real phones, and about eight for the extra security work, because the job details sit on the phone overnight and have to be encrypted.

[00:04:08] Dev: The encryption bit isn't optional, for what it's worth. Customer addresses on a phone that might get left in a café.

[00:04:19] Marcus: Understood. And is the testing negotiable?

[00:04:24] Lucy: Not really. If we don't test in the cellars, we'll find out on the first day of March that it doesn't work, which is worse.

[00:04:37] Kemi: I'll still take them down the cellars. Offer stands.

[00:04:43] Marcus: And this is where I come in. The release one budget is four hundred and ten thousand and that's fixed, it was set at the board in September. We're already at four hundred and two with the current statement of work. So thirty eight thousand doesn't fit unless something comes out.

[00:05:07] Rachel: What's the eight thousand of headroom for, at the moment?

[00:05:14] Marcus: Contingency, mostly. And I'd really rather not spend it in November.

[00:05:21] Tom: What's contingency for, if not this?

[00:05:26] Marcus: For the thing we haven't thought of yet. There's always one.

[00:05:33] Rachel: He's right. Let's not touch it.

[00:05:38] Rachel: Okay. So what can come out?

[00:05:43] Lucy: The two biggest optional pieces in release one are the SMS module and the dispatcher map view. The map is mostly dependent on the location question anyway.

[00:05:57] Dev: And the map's priced separately in the statement of work? I thought it was bundled in.

[00:06:06] Lucy: It's a separate line, about twenty two thousand, because it needs the location feed and the map licence.

[00:06:16] Marcus: So we'd be paying twenty two thousand for something we might not be allowed to use.

[00:06:25] Lucy: Potentially, yes. Which is another reason not to commit to it until the union's decided.

[00:06:34] Tom: The map's no use if we're not allowed to show where people are. That's still with the union, isn't it?

[00:06:45] Rachel: It is. The meeting with the union reps moved to the nineteenth, so nothing's changed there, it's still open. So the map can't come out to save money, because it isn't really in.

[00:07:01] Tom: I'll be honest, I'd have liked the map. But I'd rather have the lads using the app than the lads leaving their phones in the van.

[00:07:14] Kemi: That's very mature of you, Tom.

[00:07:19] Tom: I have my moments.

[00:07:23] Lucy: Then the SMS module is the obvious one. That's forty one thousand with the setup.

[00:07:32] Marcus: Why is it forty one? It's text messages.

[00:07:38] Lucy: It's the module licence for the first year, the setup with the text provider, and the templates and testing. The texts themselves are pennies. It's the plumbing that costs.

[00:07:52] Dev: And the customer phone numbers aren't clean either. Half of them are landlines. We'd have spent weeks cleaning data.

[00:08:02] Tom: My mother's number on our system is her old house. She moved in nineteen ninety eight.

[00:08:11] Kemi: But the texts were the thing customers were going to notice. That was the whole point of the two-hour window.

[00:08:22] Rachel: That's a fair point and I don't want to lose it. Customers notice the window more than how they hear about it, I think. But you're right that the text was the visible bit.

[00:08:39] Kemi: It's just, when we sold this to the lads, half of what we said was "customers will stop shouting at you on the doorstep". That was because they'd know when we're coming.

[00:08:55] Tom: The window doesn't need the text, though. We can give them the window when they book, or ring them the day before like we do now for the big jobs. The text is nice, the window's the actual thing.

[00:09:14] Kemi: Okay. As long as the desk actually tells them. Not just "sometime Tuesday".

[00:09:22] Tom: We'll tell them. It's written into the booking script, I'll change the script myself.

[00:09:30] Lucy: The window shows on the office screen when the job's booked, so the desk can read it out.

[00:09:40] Rachel: I agree with Tom. The offline viewing is what makes the app usable at all in the North. The texts can wait. So, decision: the automatic evening text to customers comes out of release one. Customers still get a two-hour arrival window, and the desk tells them when they book. We'll look at the texts again for release two.

[00:10:07] Kemi: Can that go in the notes as a promise? Release two, texts.

[00:10:14] Rachel: It'll go in the notes as the plan for release two. I can't promise a budget I haven't got yet.

[00:10:25] Kemi: Fair.

[00:10:29] Marcus: That brings you to three ninety nine. That works.

[00:10:35] Lucy: I'll reissue the statement of work with the offline viewing in and the SMS out.

[00:10:44] Marcus: And can you show the new total on the first page? The board likes the number at the top.

[00:10:54] Lucy: Of course.

[00:10:58] Dev: Do we need a change note for the charter as well? The charter still says offline is phase two.

[00:11:08] Rachel: Good catch. I'll write that up myself. Leave it with me.

[00:11:15] Marcus: Can I say something off the record, while we're here? Part of why finance is twitchy about the job records is that one of the North lads, Paul Hendry, is on a final warning for fiddling his job sheets. Overtime on jobs that never happened. So people upstairs like the idea of times being captured on the phone.

[00:11:42] Rachel: Marcus, I don't think that's for this meeting, and I'd rather it wasn't in the notes.

[00:11:51] Marcus: Fair, sorry. Just context.

[00:11:55] Kemi: For what it's worth, the lads don't mind the times being on the phone. Most of them are honest. It's one or two who spoil it.

[00:12:08] Rachel: Let's leave individuals out of it completely. The app records start and finish times because billing needs them. That's the reason, and that's the only reason.

[00:12:21] Rachel: Let's move on. Dev, photos and the asset register.

[00:12:27] Dev: So, photos. I talked to Tom. We'll allow up to ten photos per job. That covers the big digs, and it keeps the storage sensible.

[00:12:40] Lucy: Can I check what happens at eleven? Does the app stop them, or warn them?

[00:12:49] Dev: Stop them, with a message. Otherwise there's no point in a limit.

[00:12:56] Kemi: The lads will want to know which ones to delete, though. Can they choose?

[00:13:04] Lucy: They can delete any photo before they complete the job. After that the job record's closed.

[00:13:13] Kemi: That's fine.

[00:13:17] Tom: Gerald's going to be furious.

[00:13:21] Kemi: Gerald can keep his own photos on his own phone, like he does now.

[00:13:29] Dev: Actually, please don't encourage that. Photos of customers' houses on personal phones is exactly the thing we're trying to stop.

[00:13:40] Kemi: Okay, okay. I'll have a word.

[00:13:45] Tom: Ten's plenty. Nobody's taking more than ten photos of a hole.

[00:13:52] Dev: On the asset register, I was right, there's no interface for it yet and there won't be one before March. So for release one, Fieldwork will produce a weekly file of the meters swapped, with the old and new serial numbers, and the asset team imports it. It's still a lot better than paper on a Friday.

[00:14:18] Marcus: Weekly's fine for us, by the way. The register only feeds the asset valuation at the end of the quarter.

[00:14:29] Dev: And the asset team said they'd rather import a file than have something writing to their database anyway. They're very protective.

[00:14:40] Kemi: Told you. Fax machine people.

[00:14:44] Dev: It wasn't a fax machine.

[00:14:48] Lucy: A weekly export file, that's easy for us. Is it a CSV?

[00:14:55] Dev: CSV is fine.

[00:14:59] Lucy: Which columns do they need? Old serial, new serial, address, date?

[00:15:06] Dev: Those four, and the meter model. I'll send you their template, they've got one from the old paper process.

[00:15:16] Lucy: Great, I'll match that.

[00:15:20] Rachel: Good. And billing stays as we said, completed jobs go to billing at the end of each day?

[00:15:30] Dev: Yes, that's unchanged, the billing interface exists.

[00:15:35] Marcus: And it runs at night? Not during the day?

[00:15:41] Dev: Overnight batch, yes. Same window as the other billing feeds. It doesn't touch the daytime system.

[00:15:50] Rachel: Lucy, you asked about retention last time. I spoke to our records manager. Job records are kept for seven years, because they're part of the billing evidence. Photos are kept for two years, unless the job has a complaint against it, in which case they're kept with the complaint.

[00:16:13] Lucy: Seven years for records, two years for photos unless there's a complaint. That's clear, thank you.

[00:16:22] Dev: Do we delete the photos automatically after two years, or does someone have to do it?

[00:16:31] Lucy: The product can delete them automatically on a schedule. I'd suggest that, people forget.

[00:16:39] Rachel: Automatic, yes. And it needs to skip anything linked to a complaint.

[00:16:46] Lucy: That's how it works, the complaint link holds the photo.

[00:16:53] Kemi: Can I ask about the South? The South supervisors keep asking me when they're getting it. They're sick of the spreadsheet as well.

[00:17:05] Tom: They've started calling it the curse. "The curse has crashed again."

[00:17:12] Marcus: Is it the same spreadsheet?

[00:17:16] Tom: Same spreadsheet, different tab. It's got forty tabs. Nobody knows what half of them do.

[00:17:25] Rachel: Same as the brief. North and Central first, the South once release one has run for a full quarter. I don't want three districts learning it at once.

[00:17:39] Kemi: I'll tell them it's coming, at least. They'll want a date.

[00:17:46] Rachel: Tell them after the first quarter. If release one goes well, I'll give them a date in April.

[00:17:56] Tom: They'll moan, but fair enough.

[00:18:00] Lucy: One thing I wanted to check. The access notes, who writes them? Is that the desk when they book, or can technicians add them on site too? Because technicians know things the desk doesn't. "The gate sticks", that kind of thing.

[00:18:20] Kemi: The lads would love that. Half the useful notes are things you only find out when you're there.

[00:18:30] Tom: As long as they're polite. I'm not having "customer is a nightmare" on a job card that the customer can ask to see.

[00:18:42] Kemi: That's fair. There used to be a code on the old system for difficult customers, wasn't there? "DC" or something.

[00:18:53] Tom: There was, and someone wrote it on a job card a customer saw. That's why it got removed.

[00:19:03] Dev: And under data protection a customer can ask for everything we hold about them, including notes. So whatever's written, assume the customer reads it.

[00:19:15] Rachel: Let's think about that. I like the idea, but Tom's right, and there's a data protection side to what we write about customers. I don't want to decide it now. Can we come back to whether technicians can edit access notes?

[00:19:35] Lucy: When you do decide, there are a few options. Technicians suggest a note and the desk approves it, or technicians write directly, or a fixed list of notes they pick from. It's all in the product, it's just about which one you want.

[00:19:55] Rachel: Send me that as a short email, would you? I'll take it to the next meeting.

[00:20:04] Lucy: Will do.

[00:20:08] Lucy: Sure, I'll keep it open.

[00:20:12] Dev: Is the signature still optional? I want to make sure the build has it right.

[00:20:21] Rachel: Yes, signature when the customer's there, job can be closed without it. Nothing's changed on that.

[00:20:30] Kemi: And the note when they refuse. We said that last time.

[00:20:37] Rachel: Yes, a note when they refuse. Same as when nobody's in.

[00:20:44] Marcus: And just so I've got it, timesheets are definitely not in this? Because if they were it'd be a payroll project and I'd need a different budget.

[00:20:58] Rachel: Definitely not. Timesheets and overtime stay in HR.

[00:21:04] Marcus: Good. I'd have had to go back to the board and nobody wants that.

[00:21:12] Tom: Nobody ever wants to go back to the board.

[00:21:18] Tom: Right, I've got to go, I've got a van that won't start in Bramley. Do pick your Christmas menu.

[00:21:28] Dev: Is that the same van?

[00:21:32] Tom: It's always the same van.

[00:21:36] Kemi: That van should be on the pension.

[00:21:41] Rachel: Thanks all. Lucy, the new statement of work by next Wednesday, please.

[00:21:48] Marcus: And copy me in, please. I'll need it before the board pack goes out.

[00:21:56] Lucy: I'll send it to both of you.

[00:22:01] Kemi: See you all at the Railway, then. Fish for Tom.

[00:22:08] Tom: I heard that.

[00:22:12] Lucy: Will do.
