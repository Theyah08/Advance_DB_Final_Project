/**
 * Product Management JavaScript Module
 * Handles client-side product filtering, live search, and image upload previews.
 */

document.addEventListener('DOMContentLoaded', function () {
    const productSearchInput = document.getElementById('productSearchInput');
    const categoryFilter = document.getElementById('categoryFilter');
    const stockStatusFilter = document.getElementById('stockStatusFilter');
    const productsTableBody = document.getElementById('productsTableBody');
    const imageUploadInput = document.getElementById('productImageInput');
    const imagePreview = document.getElementById('imagePreviewThumb');
    const previewContainer = document.getElementById('imagePreviewContainer');

    // 1. Live Filter and Search on Products Table
    function filterProducts() {
        if (!productsTableBody) return;

        const searchTerm = (productSearchInput ? productSearchInput.value : '').toLowerCase().trim();
        const selectedCategory = categoryFilter ? categoryFilter.value : '';
        const selectedStockStatus = stockStatusFilter ? stockStatusFilter.value : '';

        const rows = productsTableBody.querySelectorAll('tr.product-row');
        let visibleCount = 0;

        rows.forEach(function (row) {
            const name = (row.getAttribute('data-name') || '').toLowerCase();
            const barcode = (row.getAttribute('data-barcode') || '').toLowerCase();
            const category = row.getAttribute('data-category') || '';
            const isLowStock = row.getAttribute('data-low-stock') === 'true';
            const isActive = row.getAttribute('data-active') === 'true';

            // Check search text match
            const matchesSearch = !searchTerm || name.includes(searchTerm) || barcode.includes(searchTerm);

            // Check category filter
            const matchesCategory = !selectedCategory || category === selectedCategory;

            // Check stock status filter
            let matchesStock = true;
            if (selectedStockStatus === 'low') {
                matchesStock = isLowStock;
            } else if (selectedStockStatus === 'in_stock') {
                matchesStock = !isLowStock;
            } else if (selectedStockStatus === 'inactive') {
                matchesStock = !isActive;
            }

            if (matchesSearch && matchesCategory && matchesStock) {
                row.style.display = '';
                visibleCount++;
            } else {
                row.style.display = 'none';
            }
        });

        // Toggle "no matching products" indicator
        const noResultsRow = document.getElementById('noResultsRow');
        if (noResultsRow) {
            noResultsRow.style.display = visibleCount === 0 ? '' : 'none';
        }
    }

    if (productSearchInput) {
        productSearchInput.addEventListener('input', filterProducts);
    }
    if (categoryFilter) {
        categoryFilter.addEventListener('change', filterProducts);
    }
    if (stockStatusFilter) {
        stockStatusFilter.addEventListener('change', filterProducts);
    }

    // 2. Image Upload Instant Preview
    if (imageUploadInput && imagePreview) {
        imageUploadInput.addEventListener('change', function (e) {
            const file = e.target.files[0];
            if (file) {
                // Validate file type
                if (!file.type.startsWith('image/')) {
                    alert('Please select a valid image file (PNG, JPG, JPEG, WEBP).');
                    imageUploadInput.value = '';
                    return;
                }

                // Check size (max 5MB)
                if (file.size > 5 * 1024 * 1024) {
                    alert('Image size exceeds 5MB limit.');
                    imageUploadInput.value = '';
                    return;
                }

                const reader = new FileReader();
                reader.onload = function (event) {
                    imagePreview.src = event.target.result;
                    if (previewContainer) {
                        previewContainer.style.display = 'block';
                    }
                };
                reader.readAsDataURL(file);
            }
        });
    }
});

/**
 * Generates a random standard barcode string for gift shop items
 */
function generateRandomBarcode() {
    const prefix = "PROS-";
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const barcodeField = document.getElementById('barcode');
    if (barcodeField) {
        barcodeField.value = prefix + randomDigits;
    }
}
