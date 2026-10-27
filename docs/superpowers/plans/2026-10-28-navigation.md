# FAQ navigation and unified footer

Goal: Add localized FAQ links to header navigation; unify homepage, blog, editorial and CMS page footers using six useful destinations and a restrained two-column link layout.
Architecture: CMS-owned navigation labels and targets; a build-time renderer keeps actual HTML links consistent. Existing company settings provide address, phones and email. Preserve language destinations and all content/URLs. Omit FAQ links when FAQ is hidden. Make mobile navigation collapse before labels overflow.
- [x] Regression check localized headers/footers, deep-page anchors, CMS edits and FAQ visibility.
- [x] Implement shared renderer, settings, CMS fields and responsive layout.
- [x] Build and run full checks, inspect homepage/article desktop and mobile menu behavior, deploy and verify live.

Validation: 55 Python checks passed. Desktop homepage/article and a 390px mobile navigation view reviewed. Live verification follows publication.
