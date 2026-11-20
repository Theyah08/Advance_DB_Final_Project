/**
 * Category Management JavaScript Module
 * Handles adding, editing in modals, and client-side category filtering.
 */

document.addEventListener('DOMContentLoaded', function () {
    const categorySearchInput = document.getElementById('categorySearchInput');
    const categoriesTableBody = document.getElementById('categoriesTableBody');

    // Live search on categories table
    if (categorySearchInput && categoriesTableBody) {
        categorySearchInput.addEventListener('input', function () {
            const query = this.value.toLowerCase().trim();
            const rows = categoriesTableBody.querySelectorAll('tr.category-row');
            let visibleCount = 0;

            rows.forEach(function (row) {
                const name = (row.getAttribute('data-name') || '').toLowerCase();
                const desc = (row.getAttribute('data-desc') || '').toLowerCase();

                if (!query || name.includes(query) || desc.includes(query)) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            const noResults = document.getElementById('noCategoryResults');
            if (noResults) {
                noResults.style.display = visibleCount === 0 ? '' : 'none';
            }
        });
    }
});

/**
 * Prepares and opens the Edit Category Modal with current values
 * @param {number} id 
 * @param {string} name 
 * @param {string} description 
 * @param {boolean} isActive 
 */
function openEditCategoryModal(id, name, description, isActive) {
    const form = document.getElementById('editCategoryForm');
    if (!form) return;

    form.action = `/categories/edit/${id}`;
    document.getElementById('edit_category_id').value = id;
    document.getElementById('edit_category_name').value = name;
    document.getElementById('edit_category_description').value = description || '';
    
    const activeCheckbox = document.getElementById('edit_category_is_active');
    if (activeCheckbox) {
        activeCheckbox.checked = isActive;
    }

    openModal('editCategoryModal');
}
