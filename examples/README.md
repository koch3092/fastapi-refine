# Examples

This directory contains example applications demonstrating fastapi-refine usage.

## Basic Usage

Run the basic example:

```bash
# Install dependencies
pip install fastapi-refine uvicorn

# Run the example
python examples/basic_usage.py
```

The example already installs `configure_refine(app)`, so package-generated CRUD and
validation errors use the Refine-friendly envelope described in the main README.

Then visit:
- API docs: http://localhost:8000/docs
- Example queries:
  - List all items: http://localhost:8000/items
  - Filter by title: http://localhost:8000/items?title_like=test
  - Filter active items: http://localhost:8000/items?is_active=true
  - Sort by price: http://localhost:8000/items?_sort=price&_order=desc
  - Pagination: http://localhost:8000/items?_start=0&_end=10
  - Legacy params (`skip`/`limit`) currently return 422
  - Search: http://localhost:8000/items?q=search+term

## Testing with Refine

To use these examples with a Refine frontend:

1. Configure Refine's simple-rest data provider to point to http://localhost:8000
2. The endpoints follow Refine's conventions automatically
3. All filters, sorting, and pagination will work out of the box
