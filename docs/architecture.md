# Architecture

- `views.py`: HTTP/API handling.
- `serializers.py`: request and response validation.
- `services.py`: business rules and orchestration.
- `repositories.py`: MongoDB queries and persistence.
- `infrastructure/`: database, email, and file storage integrations.
- `common/`: reusable helpers.

Django's default ORM and migration system target relational databases. This starter uses PyMongo repositories; Django's built-in ORM-backed admin/auth are not automatically connected to MongoDB.
