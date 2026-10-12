# Kickoff meeting: Campus Room Booking

Attendees: Dana Ruiz (Facilities Manager, project sponsor), Sam Okafor (Student Union representative), Priya Nair (IT developer), Alex Kim (product owner). Synthetic transcript; all names are fictional.

**Alex (Product owner):** Thanks for coming. Today we agree what goes into the first release of room booking.

**Dana (Facilities):** The main thing for us is ending double bookings. If two people can take the same room at the same time, we have failed.

**Priya (IT):** The booking service will reject an overlapping booking for the same room. That part is straightforward.

**Sam (Student Union):** Students mostly want a room for a single study session, usually a couple of hours before an exam.

**Sam (Student Union):** Could societies book the same room every week, say every Tuesday evening?

**Dana (Facilities):** Not in the first release. Recurring bookings make the clash rules much harder, so let's leave recurring bookings out for now and revisit after launch.

**Alex (Product owner):** Agreed. Recurring reservations are out of scope for release one.

**Dana (Facilities):** One more thing on length. The brief says four hours, but three hours is the most I want for a single booking, or rooms get hogged.

**Priya (IT):** Maybe we could also sync bookings to people's Outlook calendars? It might be nice.

**Alex (Product owner):** Possibly, but let's not commit to that today.

**Sam (Student Union):** What happens if a student books a room and doesn't turn up? Some rooms sit empty all afternoon.

**Dana (Facilities):** We need a rule for no-shows, and for how late someone can cancel, but I have to check with Student Services first.

**Alex (Product owner):** Okay, cancellation and no-shows stay open until Dana confirms.

**Dana (Facilities):** Also, my office needs to see who booked each room. Students should only see that a room is taken, not who took it.

**Alex (Product owner):** Good. Let's wrap up there.
