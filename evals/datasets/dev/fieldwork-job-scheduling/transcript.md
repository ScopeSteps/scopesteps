# Requirements workshop, Fieldwork job scheduling

Synthetic transcript; all names are fictional. Recorded and transcribed by Teams.

[00:00:04] Tom: Can everyone hear me? I've got the little spinning thing again.

[00:00:11] Kemi: Yeah, we can hear you. You're frozen on the screen though, you look like you've seen a ghost.

[00:00:21] Tom: That's just my face on a Monday. Did you get out on the river in the end, Rachel? You said you were going Saturday.

[00:00:33] Rachel: We did, for about an hour, and then it chucked it down and we sat in the car eating crisps. My son caught a weed. Very proud of it.

[00:00:47] Kemi: That's still more than I caught. My daughter had football at eight in the morning, in that wind, and they lost nine nil. Nine nil. I didn't know you could lose nine nil at under tens.

[00:01:04] Dev: You can lose anything at under tens.

[00:01:09] Rachel: Right, okay, let's make a start, Lucy's only got us till eleven. So, thanks for coming. The point of today is to agree what the first release of Fieldwork actually does for a technician and for the desk, so Lucy and her team at Brightline can firm up the build. I've got the brief up, you've all seen it. I'd like to come out of this with a list we all sign up to.

[00:01:42] Lucy: Before you dive in, would it help if I said thirty seconds about what our product already does out of the box? Just so you know what's cheap and what's expensive.

[00:01:57] Rachel: Yes, go on, that's useful.

[00:02:01] Lucy: So the core of Brightline Field is a job list on a phone, a screen for the office, and a set of connectors for billing systems and the like. The phone side was built for utilities originally, gas mainly, so a lot of what Kemi's going to say we'll have seen before. Where it gets expensive is anything that's specific to you, odd integrations, custom forms, that kind of thing. So when I ask "is that a must for March", that's why. Not because I'm trying to talk you out of things.

[00:02:42] Tom: That's fair. We've been sold things before that were "out of the box" and then the box turned out to be empty.

[00:02:54] Lucy: Ha. I've heard that one. I'll be honest with you when something's custom.

[00:03:02] Rachel: Good. And just to set expectations for everyone, I'm going to try and make decisions in the room today where I can, so we don't end up with forty actions and nothing agreed. Where I can't, I'll say so and we'll park it.

[00:03:22] Dev: Can I check who's taking notes? Because Teams is recording but I'm not sure the transcript's going to make sense of Tom.

[00:03:34] Tom: Charming.

[00:03:38] Rachel: Teams is recording, and I'll write up the decisions afterwards and send them round. Lucy, you'll get them too.

[00:03:48] Kemi: Can I ask, are the lads going to get a say on how it looks? Because last time we got a new system, the old asset tablet, nobody asked us, and it had buttons the size of a fingernail. You try pressing that with gloves on.

[00:04:10] Lucy: We do user testing with technicians as part of the build. Usually two rounds, one on paper sketches and one on the real thing. If you can give us six or eight people, that's ideal.

[00:04:27] Kemi: I can get you six. Maybe not on a Friday.

[00:04:34] Rachel: Let's make sure that happens. Kemi, can you pull together names after this?

[00:04:42] Kemi: Yeah, no bother.

[00:04:46] Lucy: Yes, and from our side the main thing is to know what's in for March and what's later, because that drives the plan and the cost. So I'll be pushing you on that, sorry in advance.

[00:05:03] Rachel: That's fine, that's what we need. Kemi, do you want to start with the technician's day, because that's the heart of it.

[00:05:15] Kemi: Yeah. So basically at the minute, right, you get a phone call at quarter to eight from Tom or whoever's on the desk, and they read you your jobs, and you write them on the back of your hand or whatever. And then half the time the order's daft, you're driving past one job to get to another. So what the lads want, first thing, is to open the phone and see the day, in order, with the address and how to get in. The access notes are massive. "Key under the blue pot", "dog in the garden, ring first", that kind of thing.

[00:06:01] Tom: And the parts. If it's a meter swap they need to know which meter before they leave the depot, otherwise they're driving back for it.

[00:06:14] Kemi: That's a big one, honestly. Last week Steve had a job in Thornbury that said "meter exchange" and nothing else. Turned up, it was one of the old Kent meters, the big ones, and he had the small ones in the van. Back to the depot, forty minutes each way, job pushed to the afternoon, customer furious because they'd taken the morning off.

[00:06:43] Tom: And that's on us really, because the desk knows which meter it is, it's on the asset sheet, it just never gets passed on.

[00:06:55] Lucy: So the parts would come from the job itself, whatever the desk puts on it when the job's created?

[00:07:05] Tom: Yeah, the desk or the planning team when it's a planned job. For emergencies we won't know, obviously, you find out when you dig.

[00:07:17] Dev: The asset sheet has the meter model for most addresses. Not all. There's a lot of gaps in the old villages.

[00:07:28] Kemi: There's a lot of gaps in the old villages full stop.

[00:07:35] Rachel: Okay, so the parts are whatever's on the job when it's created. If the desk doesn't know, it's blank, and the technician finds out on site like now. We're not solving the asset data in this project.

[00:07:53] Dev: Thank you. I was worried that was about to become my problem.

[00:08:00] Kemi: Yeah, the parts for the job, so you can check the van before you go.

[00:08:09] Rachel: Okay. So the day's jobs on the phone, in the order they should do them, with the address, the access notes and the parts. I think that's the core of release one, is everyone agreed?

[00:08:26] Dev: Agreed. The order comes from the desk though, right? We're not doing route optimisation.

[00:08:34] Tom: The desk sets the order. We know the patches better than any algorithm, honestly.

[00:08:42] Kemi: That's true, to be fair. Tom knows which streets have the school run at quarter to nine and which ones you can't park in. No app's going to know that.

[00:08:57] Lucy: The product can suggest an order, if you ever want it, but it's switched off by default and honestly most of our customers leave it off.

[00:09:10] Tom: Leave it off.

[00:09:14] Dev: I'd like to know how the order gets to the phone, though, technically. Is it the desk dragging jobs into a list, or a number on each job?

[00:09:28] Lucy: It's a drag and drop list on the office screen, per technician. The phone shows exactly that order. If the desk moves a job up, it moves up on the phone.

[00:09:43] Tom: That's basically the spreadsheet but without me having to ring everyone. Fine by me.

[00:09:51] Rachel: Good, that's settled then. Let's move on.

[00:09:56] Lucy: Good, because route optimisation is a whole other product. So the order is whatever the dispatcher sets, and the technician sees it.

[00:10:08] Rachel: Yes. Desk sets the order.

[00:10:12] Kemi: Can I just say while we're on the North, we're two down this week anyway. Gary's off with his back again, the disc thing, and he's waiting on the scan, so that's why North looks so thin on the sheet. Not that that's a Fieldwork thing.

[00:10:34] Rachel: Thanks Kemi, let's maybe keep that one for the team meeting.

[00:10:41] Tom: Speaking of which, is anyone covering North on Thursday? Because I've got two jobs in Easton I can't place.

[00:10:51] Kemi: Ask Daz. He said he'd do overtime this week.

[00:10:57] Tom: Daz said that last week and then went to his sister's wedding.

[00:11:04] Rachel: Can we take the rota offline, please? Tom, you were going to do the desk side.

[00:11:13] Kemi: Yeah, sorry, sorry.

[00:11:17] Rachel: No, it's fine. Tom, the desk side.

[00:11:22] Tom: So for us the big one is moving work about during the day. Someone gets stuck on a burst that takes four hours instead of one, and I've got three jobs sat behind him. At the minute I'm ringing round. What I want is to see every job and where it's up to, started, finished, stuck, whatever, and just drag a job from one technician to another, and it turns up on their phone.

[00:11:55] Lucy: And the technician gets told it's changed? A notification?

[00:12:01] Tom: Yeah, it has to buzz, they're not staring at the phone when they're up to their knees in a hole.

[00:12:12] Kemi: Can it be a proper loud one? Not a little ding. If you're on a pumping station with the generator going you'll never hear a ding.

[00:12:25] Lucy: The phone uses whatever notification sound the technician sets. We can't override that, Apple and Android won't let us. But we can make it vibrate as well.

[00:12:39] Kemi: Vibrate's good. Most of the lads have it in the top pocket.

[00:12:46] Dev: Do we need them to say they've seen it? Like an acknowledge button, so Tom knows they've seen the change?

[00:12:57] Tom: That would be nice. At the minute I ring and they say "yeah, yeah" and then I find out an hour later they didn't hear me.

[00:13:10] Lucy: There's a read marker in the product already. The office sees when the technician has opened the change. It's not a big thing, it comes with it.

[00:13:24] Rachel: That's fine, if it comes with it. I'm not going to make a big deal of it either way.

[00:13:34] Rachel: So dispatchers can see the status of every job and reassign a job to another technician during the day, and the technician gets a notification when their list changes. Yes.

[00:13:49] Dev: Who's allowed to reassign, just the supervisors or anyone on the desk?

[00:13:56] Tom: Anyone on the desk. There's five of us and I'm not always in.

[00:14:04] Kemi: As long as they're not moving my jobs while I'm driving to them. Last month I got sent to Coalpit Lane, got there, and someone had given it to Mike while I was on the motorway.

[00:14:21] Tom: That was a one-off.

[00:14:25] Kemi: It was twice.

[00:14:29] Tom: It was twice. Fair.

[00:14:33] Lucy: Once it's reassigned, the job disappears from the first technician's list and they get the notification, so at least you'd know before you got there. Not after.

[00:14:47] Kemi: That's already better than now.

[00:14:51] Rachel: Let's say any dispatcher. Fine.

[00:14:55] Kemi: Now this is the bit I really care about. Signal. Half the North is no signal. The new estates are fine but the old village streets, the cellars where the meters are, the pumping stations, nothing. If the app needs signal to show you your jobs, it's dead in the water. Pun intended.

[00:15:19] Tom: She's not exaggerating. I've got a list on the wall of the dead streets. Old Market, the whole of Cotham Hill, the cellars on Victoria Street. You lose signal at the top of the steps.

[00:15:36] Dev: And the pumping stations are basically Faraday cages. Concrete and steel. Even the radios struggle.

[00:15:45] Lucy: How do the technicians get their jobs there today?

[00:15:51] Kemi: We don't, that's the point. You write it on your hand, like I said. Or you go back up to the road and ring Tom.

[00:16:04] Rachel: How many jobs a day are we talking about in those places?

[00:16:11] Tom: In the North, maybe one in five. Central's better, maybe one in ten.

[00:16:19] Rachel: One in five is a lot.

[00:16:24] Lucy: So, on that, in the statement of work offline mode is in phase two, not March. It's a big chunk of work, because you're syncing changes both ways and handling conflicts.

[00:16:39] Kemi: Then March is no good to us, to be honest.

[00:16:46] Dev: Could we split it? Seeing your day without signal is much easier than editing without signal. You download the day in the morning at the depot, and it's there.

[00:17:00] Lucy: Read-only offline is a lot less work, yes. Editing offline, completing jobs offline, that's the hard part.

[00:17:10] Kemi: Seeing it is the main thing. If I can see the job and the access notes in a cellar, I can fill the rest in when I'm back up the steps.

[00:17:25] Rachel: Okay. Then I'm going to make a call on this. The technician can see their day's jobs without signal in the first release. Completing a job without signal waits for phase two. Lucy, I know that's not in the statement of work as it stands, so you'll need to price it.

[00:17:49] Lucy: I'll price it this week. I'll warn you now it won't be free.

[00:17:57] Dev: When you price it, can you split out the testing? Because testing in those streets is going to be half the work. You can't simulate a cellar.

[00:18:11] Lucy: Good point. I'll put the field testing as its own line so you can see it.

[00:18:20] Kemi: I'll take your testers down a cellar myself. Bring a torch.

[00:18:27] Rachel: Ha. Thank you Kemi. Okay, Tom's back in a minute, let's keep going.

[00:18:35] Rachel: Understood.

[00:18:39] Tom: Can I go and put the kettle on? I'm going to miss the next bit otherwise, I've been on since six.

[00:18:50] Rachel: Go on, two minutes. Kemi, carry on with the job record while Tom's out.

[00:18:58] Kemi: So when you finish a job, right, at the minute you fill the paper sheet: what you did, what parts you used, start and finish time, and the customer signs if they're in. Then it sits in the van till Friday. So we want to do that on the phone, and take photos. Photos are big, because if there's a complaint later, "you left my drive in a state", we've got proof.

[00:19:30] Lucy: Photos attached to the job record. How many per job?

[00:19:37] Kemi: And they need to be decent. The old tablet took photos like a potato. You couldn't tell a drive from a lawn.

[00:19:49] Lucy: It uses the phone's own camera, so it's as good as the phone. What are the company phones, the Samsung ones?

[00:20:00] Dev: The A-series, about two years old. The camera's fine.

[00:20:06] Kemi: Fine's fine. As long as you can see the hole.

[00:20:13] Kemi: Depends, two or three usually. Sometimes more on a big dig.

[00:20:20] Dev: We'll want a limit, for storage. I'll check with Tom what's sensible.

[00:20:27] Lucy: For what it's worth, our other customers usually set something between five and fifteen. It's not a technical limit, it's just about storage and keeping people from taking forty photos of the same hole.

[00:20:44] Rachel: We'll come back to a number. Dev and Tom can agree it.

[00:20:51] Kemi: Some of the lads would take forty, to be fair. Gerald photographs everything. He's got photos of every manhole in the district. It's like a hobby.

[00:21:04] Tom: It's not like a hobby, it is a hobby. He showed me a calendar.

[00:21:12] Rachel: Fine. So the technician completes the job record on the phone, what was done, the parts used and the times, with photos attached.

[00:21:24] Kemi: And the signature. Honestly half the time there's nobody in. You can't make the customer signing compulsory or you can never close a job.

[00:21:36] Rachel: Is that a problem for billing, Dev? Does billing need the signature?

[00:21:43] Dev: No. Billing needs the job closed and the parts. The signature is more of a nice-to-have for complaints.

[00:21:53] Lucy: And if the customer's there but refuses to sign? It happens.

[00:22:00] Kemi: Oh, it happens. Usually because they're annoyed about something that's nothing to do with us. Then you put a note.

[00:22:11] Rachel: Then the technician closes the job without it and adds a note, same as if nobody's in.

[00:22:21] Rachel: Signature when the customer's there, then, and the job can be closed without one.

[00:22:29] Lucy: Optional signature. Got it.

[00:22:33] Tom: I'm back. What did I miss? Did we agree we're all getting a pay rise?

[00:22:42] Kemi: Ha, I wish. We're not paid enough to be chasing customers for signatures, I'll tell you that for nothing.

[00:22:52] Rachel: Let's not go there today. Customers next. The brief says a two-hour window instead of eight till six. Tom, how would that actually work?

[00:23:04] Tom: Can I just say before customers, I've been thinking about the kettle problem.

[00:23:12] Rachel: The what?

[00:23:16] Tom: The kettle on our floor. It takes eight minutes to boil. We've asked facilities three times.

[00:23:25] Rachel: Tom.

[00:23:29] Tom: Sorry. Customers.

[00:23:33] Tom: So if the order's set the night before, we can work out roughly when each job lands. Two hours either side of that is honest. At the minute we tell them all day because we don't know.

[00:23:51] Kemi: Honestly, the all day thing is what kills us on the doorstep. People take a day off work for a ten minute job and they're livid before you've even got the van door open. If they knew it was nine till eleven, half the arguments would never happen.

[00:24:13] Lucy: Do customers ring the desk a lot asking where the technician is?

[00:24:20] Tom: Constantly. Probably a third of our calls on a busy day are "where's my engineer". And we don't know either, so we ring the engineer, and round and round it goes.

[00:24:35] Dev: If the window's on the job, could the desk see it next to the status? So when someone rings, the desk can say "he's on his way, he's in your window"?

[00:24:50] Tom: That would cut those calls right down.

[00:24:55] Lucy: The office screen shows the window and the status side by side. That's standard.

[00:25:03] Rachel: Good. Then the desk can answer those calls without ringing round.

[00:25:10] Lucy: We could send the customer a text the evening before with their two-hour window. That's standard in the product, we've got an SMS module.

[00:25:22] Tom: How much do the texts cost, though? Per text, I mean.

[00:25:29] Lucy: Pennies each, it's the module and the setup that cost. I'll include it in the pricing.

[00:25:38] Rachel: Marcus would ask about that, if he were here.

[00:25:44] Rachel: That's what I had in my head, yes. The customer gets a two-hour arrival window, and a text the evening before telling them.

[00:25:56] Dev: Do we need them to be able to reply to it? Like rebook?

[00:26:04] Lucy: Rebooking by text is a different feature. That's not in the module out of the box.

[00:26:13] Dev: I was going to say, we could put a little chatbot on the website, so customers can rebook themselves. Takes a load off the desk.

[00:26:26] Tom: A chatbot. For our customers. Half of them still ring to ask if the water's safe after a tap's been off.

[00:26:37] Kemi: That's true, to be fair. My nan rang them last week. She's eighty-eight. She doesn't know what a chatbot is and she doesn't want to.

[00:26:50] Dev: Okay, okay, I'm outnumbered. It was just a thought.

[00:26:56] Tom: It's a good thought for the website team. Not for us.

[00:27:03] Rachel: Let's park the chatbot. Not for March. It's an idea for later, maybe.

[00:27:11] Dev: Fair. I'll write it down somewhere.

[00:27:16] Rachel: Emergencies. Tom, this is where it gets interesting.

[00:27:22] Tom: So when a burst comes in, I need to send the nearest free person. At the minute I'm guessing from the sheet where everyone is. If the app could show me where everyone is on a map, I'd send the right person every time.

[00:27:43] Kemi: How often does that actually happen, though? Like a proper burst?

[00:27:50] Tom: Proper burst, two or three a day across the North and Central. Plus the smaller stuff that's still urgent, a leak in someone's kitchen, no water to a street. Maybe ten a day that I'd call emergencies.

[00:28:08] Lucy: And today you decide who goes based on what?

[00:28:14] Tom: Based on the sheet and my memory. Who started where, who's probably finished, who's on a long job. Half the time I'm wrong and someone's sat in a lay-by having finished early while I send someone from the other side of the patch.

[00:28:34] Kemi: Yeah, so this is the bit the lads are worried about. Nobody wants to be tracked all day. Where you stop for your dinner, how long you're in the cafe. There's a lot of people saying if the phone's tracking them they'll leave it in the van.

[00:28:56] Tom: I don't care where they have their dinner, I care where the burst is.

[00:29:04] Kemi: I know you don't, but it's not you, is it, it's whoever has the data after you.

[00:29:14] Kemi: And there's history, isn't there. The vans had trackers put in about five years ago and someone in management used it to have a go at Pete for stopping at his mum's. On his dinner. That's why people are twitchy.

[00:29:33] Rachel: I remember. That shouldn't have happened, and it's exactly why I'm not deciding this without the union.

[00:29:43] Dev: The van trackers are still there, aren't they? Technically we already know where the vans are.

[00:29:52] Kemi: The van, yeah. Not the person. There's a difference, to the lads anyway.

[00:30:00] Lucy: From a product point of view, location can be switched off completely, or on only when a job's in progress, or on all day. So whatever you decide with the union, it can do it. I just need to know before we test.

[00:30:20] Rachel: This is a real concern and I don't want to decide it in this room. The union reps need to be part of it. What I will say is the desk can flag a job as an emergency and it goes to the top of a technician's list. Whether we show technicians' locations on a map, and when, is open until we've talked to the union.

[00:30:50] Lucy: So for the build, emergency flag yes, live location undecided.

[00:30:57] Rachel: Correct.

[00:31:01] Tom: When's the union meeting?

[00:31:05] Rachel: I'm trying to get one on the twelfth. I'll let everyone know.

[00:31:12] Kemi: Ask for Bob, not Graham. Bob's reasonable. Graham will want it in writing in triplicate.

[00:31:21] Rachel: Noted.

[00:31:25] Dev: Can I raise one on the systems side? Billing. The whole point is to stop waiting for the paper. So when a job's completed, the record needs to go to the billing system. I'd say end of each day is fine, it doesn't need to be instant.

[00:31:47] Rachel: End of day is fine for billing.

[00:31:52] Dev: Today billing's about ten days behind the work, because of the paper. Finance hate it. They're chasing customers for jobs we did a fortnight ago, and the customer's forgotten.

[00:32:06] Lucy: So nightly is a big improvement for them already.

[00:32:12] Dev: Huge. They'll throw a party. Well, they'll send a slightly less angry email.

[00:32:20] Dev: And the asset register as well, when a meter's swapped, the new meter serial has to go on the register.

[00:32:31] Lucy: We'll need the register's interface spec for that. I've not seen one.

[00:32:38] Dev: There isn't really one yet. That's my problem, not yours. Leave it with me.

[00:32:46] Rachel: Dev, can you give me an answer on the register by the next meeting? Even if the answer is "it can't be done for March".

[00:32:59] Dev: Yes. I'll talk to the asset team this week.

[00:33:05] Kemi: Good luck. The asset team still use fax, I swear.

[00:33:12] Dev: They don't use fax.

[00:33:16] Kemi: They used fax last year.

[00:33:20] Dev: That was one time.

[00:33:24] Kemi: What about timesheets? If we're doing everything on the phone, can we do our hours and overtime on it as well? We still do overtime on a paper form.

[00:33:38] Rachel: No. Timesheets and overtime stay in the HR system. I don't want Fieldwork anywhere near pay. That's a firm no for this project.

[00:33:50] Kemi: Worth a try.

[00:33:54] Lucy: One more for me. How long do we keep the job records and photos? Is it forever, seven years, something else? It affects the storage cost.

[00:34:07] Rachel: I genuinely don't know. That's a question for our records manager. Can I come back to you?

[00:34:17] Dev: I think it's seven years for anything financial, but I'm not sure that covers photos.

[00:34:26] Rachel: I'd rather ask than guess. I'll ask Sandra.

[00:34:32] Lucy: Of course. I'll put it down as open.

[00:34:38] Tom: Before we wrap up, are we still doing the depot car park thing next week? Because I'm not parking on the road again, I got a ticket last time.

[00:34:52] Rachel: That's facilities, Tom, I'll chase them. Right. Let me read back what I've got. Day's jobs on the phone in the desk's order, with address, access notes and parts. Dispatchers see every job's status and any dispatcher can reassign, technician gets a notification. Day's jobs visible without signal in March, completing without signal is phase two. Job record on the phone with photos, signature optional. Two-hour window with a text the night before. Emergency flag puts a job top of the list. Completed jobs to billing at the end of each day. Asset register, Dev's looking into. No timesheets or overtime. Chatbot parked. Location tracking open until the union meeting. Retention open. Have I missed anything?

[00:35:43] Lucy: Before you read back, can I check one practical thing? Training. How do the technicians learn this? Do you want us to do it, or do you have trainers?

[00:35:57] Rachel: We've got two trainers in the depot. I'd like your team to train them, and they train everyone else.

[00:36:07] Lucy: Train the trainer, fine. I'll put two days in the plan.

[00:36:14] Kemi: Do it in the morning. Nobody learns anything after a full shift.

[00:36:21] Rachel: Good shout. Right, let me read back.

[00:36:26] Kemi: That's it. That's actually loads.

[00:36:30] Tom: It is loads. Are we really going to get all that by March?

[00:36:38] Lucy: If the offline viewing prices sensibly and the register sorts itself out, yes. I'll be straight with you if it's not.

[00:36:49] Rachel: That's all I ask.

[00:36:53] Lucy: That's very clear, thank you. I'll send the pricing for offline viewing by Friday.

[00:37:01] Rachel: Thanks everyone. Same time in two weeks.
