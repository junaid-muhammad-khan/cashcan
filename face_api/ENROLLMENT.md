# Enrolling with only 1 to 3 photos

Real users will take **1 photo, or 3 at most**, not a guided 13-frame session. The API and web page now accept 1-3 photos (`MIN_ENROLL_FRAMES = 1`,
`MAX_ENROLL_FRAMES = 3`; the web page takes 3 quick pictures). This file records what was measured about doing recognition from so few photos.

## 1. How accuracy depends on the number of photos (LFW press photos, 150 people, 777 probe photos, 858 stranger photos)

Recognised enrolled people by number of enrollment photos and match threshold. **Wrong names were 0 in every cell.**
Strangers accepted was 1 of 858 in every cell from 35% up: that one is a photo labelled Rosalyn Carter that also shows Jimmy Carter (enrolled), so the match is correct.

| Photos at enrollment | 35% | 40% | 45% (default) | 50% |
|---|---|---|---|---|
| 1 | 98.8% | 96.9% | 93.6% | 87.1% |
| 2 | 99.6% | 99.2% | 97.8% | 95.0% |
| 3 | 99.7% | 99.5% | 99.0% | 97.7% |

Fewer photos means lower scores for the right person, so the threshold costs more recognition. At 30% strangers start to get in (21 of 858), so 35% is close to
the edge; 40% leaves a wider margin. The default stays at 45% until a friend or lookalike has been tested.

## 2. What is saved matters more than how many photos (real data: one person, 26 real webcam frames)

Each row is scored on the webcam frames *not* used to enroll, averaged over 400 random draws. The frames include far, dim, side-lit and turned ones (a hard test).

| How the person enrolled | Median live score | Frames recognised at 45% |
|---|---|---|
| 1 phone or studio photo | 55% | 81% |
| 3 "photos" that are variants of the same photo | 55% | 81% (no gain) |
| 1 selfie from the bin camera (any frame) | 62% | 81% |
| 1 selfie from the bin camera, an ordinary frontal one | 69% | 90% |
| 1 studio photo + 2 bin-camera frames | 69% | 92% |
| 3 bin-camera frames | 72% | 92% |

**Guidance that follows:**
- Enroll with the same kind of camera the bin uses, ideally at the bin itself. One ordinary frontal frame from that camera recognises 90% of later frames; a studio photo only 81%.
- If 3 photos are taken, they must be genuinely different (pose, light). Copies or variants of one photo add nothing.

## 3. What does NOT help with one photo
Adding copies of the photo degraded to look like a webcam (noise, JPEG, dim, warm and cool light, low resolution, blur), flip-averaging the template, or lighting and zoom variants
all left the real webcam frames at a median of 55-56% and 22 of 26 above 45%. The gap between a studio photo and a webcam is not simple noise or lighting.

## 4. Not built: self-updating templates
After a very confident match the bin could add that live frame to the person's saved set, so the profile drifts toward the bin camera. On the same real frames, starting from one
studio photo and adding frames that scored at least 55% (up to 10), recognition over a session rose from 81% to 91% at 45%. Higher add-thresholds (65%, 75%) never fire from a studio
photo because no webcam frame scores that high. It is **not built** because it needs: explicit consent (more biometric data is stored over time), a cap and expiry, liveness before any update,
an unambiguous-match rule, and a way to see and undo what was added. The risk is drift or poisoning: a lookalike's frame accepted once would make that person easier to impersonate.

## Caveats
Section 2 and 4 use one person's frames (26) and are indicative, not statistics. Section 1 uses press photos. Lookalikes, siblings and spoofing were not tested.
