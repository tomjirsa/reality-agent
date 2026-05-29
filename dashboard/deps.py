import unicodedata
from pathlib import Path
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def sreality_url(listing) -> str:
    raw = listing.raw_json or {}
    seo = raw.get("seo", {})
    locality = seo.get("locality", "")
    if not locality:
        # v1 API has no seo key; derive locality slug from the locality.city field
        city = raw.get("locality", {}).get("city") or ""
        locality = city.lower().replace(" ", "-")
    type_name = "pronajem" if listing.category_type_cb == 2 else "prodej"
    main_name = "dum" if listing.category_main_cb == 2 else "byt"
    sub_name = (raw.get("category_sub_cb") or {}).get("name", "")
    if sub_name:
        sub_slug = unicodedata.normalize("NFD", sub_name.lower())
        sub_slug = "".join(c for c in sub_slug if unicodedata.category(c) != "Mn")
        sub_slug = sub_slug.replace(" ", "-")
    else:
        sub_slug = "rodinny-dum" if listing.category_main_cb == 2 else "3+kk"
    if locality:
        return f"https://www.sreality.cz/detail/{type_name}/{main_name}/{sub_slug}/{locality}/{listing.hash_id}"
    return f"https://www.sreality.cz/detail/{type_name}/{main_name}/{listing.hash_id}"


templates.env.globals["sreality_url"] = sreality_url
