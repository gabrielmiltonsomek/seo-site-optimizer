# seo-site-optimizer
SEO Site Optimizer Engine

This is not the fully operational version, the purpose of this repository is to showcase the code.

This project is a backend-driven website optimization engine built in Python using Flask. It is designed to programmatically enhance static websites by injecting structured SEO metadata, normalizing HTML head elements, and optimizing front-end assets to improve performance and search engine visibility.

This repository contains a preview version of the core processing logic. It is not intended to function as a fully deployable production application. The purpose of this repository is to demonstrate architectural design, backend automation, and structured optimization techniques.

The system is designed to process a static website archive and apply transformations across HTML, CSS, JavaScript, image assets, and configuration files. The core functionality includes dynamic SEO metadata generation, structured data injection using JSON-LD, Open Graph tag generation, canonical URL normalization, and automated sitemap and robots.txt creation.

The HTML processing pipeline parses documents using BeautifulSoup, removes redundant or outdated metadata, and reconstructs a standardized head section. The system ensures proper charset and viewport configuration while injecting updated metadata and structured schema definitions compliant with Schema.org standards.

Performance enhancements are applied programmatically across the asset layer. Images are compressed and recompressed using Pillow to reduce file size and improve load performance. JavaScript files are sanitized and whitespace-minified to reduce payload size. CSS files undergo comment stripping and compression. Images are configured with lazy loading attributes, and scripts are automatically assigned defer behavior where appropriate to reduce render-blocking behavior.

The application implements recursive file-system traversal to apply transformations across entire directory structures. XML sitemap generation is handled through ElementTree, dynamically mapping discovered HTML files to canonical URLs with updated modification timestamps. The system also scaffolds basic Progressive Web App assets including a manifest file and service worker stub to improve installability and structural completeness.

The public version of this repository intentionally omits production deployment configuration, hosting setup, hardened security measures, and environment management. It serves as a technical preview to demonstrate backend architecture, automated optimization logic, and scalable content transformation design.

The project is implemented using Python 3, Flask, BeautifulSoup4, Pillow, and standard XML processing libraries.

This project is licensed under the MIT License.
