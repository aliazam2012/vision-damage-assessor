import datetime as dt
import io

from freight_agents.damage_assessor.domain import Finding
from freight_agents.damage_assessor.extract import Photo, extract, prepare_photo
from freight_agents.llm import ImagePart, ModelTurn, ScriptedModel, Usage
from PIL import Image

NOW = dt.datetime(2026, 11, 25, 9, 0, tzinfo=dt.UTC)


def image_bytes(size: tuple[int, int], fmt: str, mode: str = "RGB") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, (200, 150, 90)).save(out, format=fmt)
    return out.getvalue()


def test_a_photo_within_limits_passes_through_byte_for_byte() -> None:
    data = image_bytes((640, 480), "JPEG")
    prepared = prepare_photo(Photo(name="p.jpg", media_type="image/jpeg", data=data))
    assert prepared is not None
    assert prepared.data == data
    assert prepared.media_type == "image/jpeg"


def test_the_media_type_comes_from_the_bytes_not_the_name() -> None:
    data = image_bytes((320, 240), "JPEG")
    prepared = prepare_photo(Photo(name="looks-like.png", media_type="image/png", data=data))
    assert prepared is not None
    assert prepared.media_type == "image/jpeg"


def test_a_large_photo_is_downsized_to_a_1568_pixel_long_edge() -> None:
    prepared = prepare_photo(Photo("big.png", "image/png", image_bytes((4000, 3000), "PNG")))
    assert prepared is not None
    with Image.open(io.BytesIO(prepared.data)) as im:
        assert max(im.size) == 1568
        assert im.format == "JPEG"
    assert prepared.media_type == "image/jpeg"


def test_a_type_the_api_does_not_accept_is_converted_to_jpeg() -> None:
    tiff = image_bytes((300, 200), "TIFF")
    prepared = prepare_photo(Photo("scan.tiff", "image/tiff", tiff))
    assert prepared is not None
    assert prepared.media_type == "image/jpeg"
    rgba = prepare_photo(Photo("x.bmp", "image/bmp", image_bytes((50, 50), "BMP")))
    assert rgba is not None
    assert rgba.media_type == "image/jpeg"


def test_bytes_that_are_not_a_readable_image_are_not_sent() -> None:
    assert prepare_photo(Photo("IMG_0001.HEIC", "image/heic", b"ftypheic not decodable")) is None


def test_an_unreadable_photo_gets_a_null_finding_and_is_never_sent() -> None:
    usage = Usage()
    model = ScriptedModel(
        [ModelTurn(text="", tool_calls=[], stop="end", usage=usage, model="scripted")]
    )
    photos = [
        Photo("ok.jpg", "image/jpeg", image_bytes((64, 64), "JPEG")),
        Photo("IMG_0001.HEIC", "image/heic", b"ftypheic not decodable"),
    ]
    result = extract(photos, "", model, NOW)
    sent = [p for p in model.calls[0].messages[0].parts if isinstance(p, ImagePart)]
    assert len(sent) == 1
    assert Finding(photo="IMG_0001.HEIC", confidence=0.0) in result.findings
