# Damage Images

## Table of Contents

- [What Is Here](#what-is-here)
- [Synthetic Images](#synthetic-images)
- [Licensed Photos](#licensed-photos)
- [Labels](#labels)

---

## What Is Here

The images damage-assessor is tested and evaluated on: synthetic photos drawn from a seed, whose labels are the ground truth they were drawn from, and openly licensed photos from Wikimedia Commons with hand labels. No image here comes from a real claim.

## Synthetic Images

`synthetic/` holds 50 PNGs drawn with Pillow by `data/generate_damage.py` (seed 2026): cartons and pallets with crushed, punctured, wet, torn and shifted damage at set severities, intact ones, concealed damage inside an opened carton, inadequate packaging (an untaped carton, a load hanging over its pallet), two blank frames, a delivery receipt, and three red-team images with instructions written on the freight. They are synthetic and labeled as such in `synthetic/labels.jsonl`. They are part of this repository and share its MIT license.

## Licensed Photos

`licensed/` holds photos under a public-domain or attribution-only license, downsized by `data/fetch_licensed_photos.py`. Share-alike, no-derivatives and non-commercial licenses are not accepted. The photos keep their own licenses, not this repository's: credit each one as below when you reuse it.

| Image | Title | Author | License | Source | Changes |
|---|---|---|---|---|---|
| `sdasm-0051333.jpg` | 23 0051333 Convair Negative Image - Damaged packaging (53889404456).jpg | San Diego Air & Space Museum Archives | Public domain | https://commons.wikimedia.org/wiki/File:23_0051333_Convair_Negative_Image_-_Damaged_packaging_(53889404456).jpg | Downsized to at most 640 pixels on the long side and saved as JPEG |
| `sdasm-0073143.jpg` | 23 0073143 Convair Negative Image - Damaged packaging (54268196061).jpg | San Diego Air & Space Museum Archives | Public domain | https://commons.wikimedia.org/wiki/File:23_0073143_Convair_Negative_Image_-_Damaged_packaging_(54268196061).jpg | Downsized to at most 640 pixels on the long side and saved as JPEG |
| `nara-17421500.jpg` | DAMAGED OIL PUMP PACKAGE - NARA - 17421500.jpg | Unknown photographer, U.S. National Archives and Records Administration | Public domain | https://commons.wikimedia.org/wiki/File:DAMAGED_OIL_PUMP_PACKAGE_-_NARA_-_17421500.jpg | Downsized to at most 640 pixels on the long side and saved as JPEG |
| `open-logistics-epal.jpg` | DB EPAL pallet broken.jpg | Open Logistics from ITALIA | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) | https://commons.wikimedia.org/wiki/File:DB_EPAL_pallet_broken.jpg | Downsized to at most 640 pixels on the long side and saved as JPEG |
| `meanwell-fragile-box.jpg` | Damaged Cardboard Box Labelled Fragile.jpg | Meanwell Packaging | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) | https://commons.wikimedia.org/wiki/File:Damaged_Cardboard_Box_Labelled_Fragile.jpg | Downsized to at most 640 pixels on the long side and saved as JPEG |
| `meanwell-doorstep.jpg` | Damaged fragile parcel delivered to doorstep.jpg | Meanwell Packaging | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) | https://commons.wikimedia.org/wiki/File:Damaged_fragile_parcel_delivered_to_doorstep.jpg | Downsized to at most 640 pixels on the long side and saved as JPEG |
| `meanwell-corridor.jpg` | Fragile Parcel left outside door.jpg | Meanwell Packaging | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) | https://commons.wikimedia.org/wiki/File:Fragile_Parcel_left_outside_door.jpg | Downsized to at most 640 pixels on the long side and saved as JPEG |
| `smithsonian-parcel-post.jpg` | Photograph of damaged packages (that) slow up the mail service (4010662407).jpg | Smithsonian Institution (Flickr Commons) | [No restrictions](https://www.flickr.com/commons/usage/) | https://commons.wikimedia.org/wiki/File:Photograph_of_damaged_packages_(that)_slow_up_the_mail_service_(4010662407).jpg | Downsized to at most 640 pixels on the long side and saved as JPEG |
| `hah-postal-notice.jpg` | Post Paeckchen beschaedigt.png | HAH (Wikimedia Commons user) | Public domain | https://commons.wikimedia.org/wiki/File:Post_Paeckchen_beschaedigt.png | Downsized to at most 640 pixels on the long side and saved as JPEG on a white background |

## Labels

Every image has one label in the shape of a `Finding` (damage type, severity, packaging, visible or concealed, confidence), with null wherever the image cannot say. Synthetic labels carry confidence 1.0. Hand labels on the licensed photos carry the labeler's confidence: a photo people could disagree on is labeled below 1.0, and its note says why. Two licensed images are not freight on purpose (machinery, a postal notice whose text claims damage), to test that such images yield no findings.
