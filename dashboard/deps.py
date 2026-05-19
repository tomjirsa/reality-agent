from pathlib import Path
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def sreality_url(listing) -> str:
    seo = (listing.raw_json or {}).get("seo", {})
    locality = seo.get("locality", "")
    type_name = "pronajem" if listing.category_type_cb == 2 else "prodej"
    main_name = "dum" if listing.category_main_cb == 2 else "byt"
    # Use a valid placeholder sub-slug; sreality redirects to the correct one
    sub_slug = "chata" if listing.category_main_cb == 2 else "3+kk"
    if locality:
        return f"https://www.sreality.cz/detail/{type_name}/{main_name}/{sub_slug}/{locality}/{listing.hash_id}"
    return f"https://www.sreality.cz/detail/{type_name}/{main_name}/{listing.hash_id}"


templates.env.globals["sreality_url"] = sreality_url
