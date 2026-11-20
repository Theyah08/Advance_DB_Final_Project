/**
 * Point of Sale (POS) Interactive Terminal Module
 * Prosfora Gift Shop POS System - Part 2
 * Handles cart management, barcode scanner input, live change calculation,
 * and AJAX ACID checkout processing.
 */

// In-memory Shopping Cart State
let cart = [];
const TAX_RATE = 0.12; // 12% Value Added Tax

document.addEventListener('DOMContentLoaded', function () {
    const barcodeInput = document.getElementById('posBarcodeInput');
    const cashInput = document.getElementById('amountTenderedInput');
    const discountInput = document.getElementById('discountInput');
    const searchInput = document.getElementById('posSearchInput');

    // 1. Auto-focus barcode scanner input on load
    if (barcodeInput) {
        barcodeInput.focus();

        // Handle Barcode Scanner Enter Key
        barcodeInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const code = this.value.trim();
                if (code) {
                    addProductByBarcode(code);
                    this.value = '';
                }
            }
        });
    }

    // 2. Real-time Product Search in Grid
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            filterProductGrid(this.value);
        });
    }

    // 3. Real-time Cash Tendered & Change Calculation
    if (cashInput) {
        cashInput.addEventListener('input', updateChangeCalculation);
    }

    if (discountInput) {
        discountInput.addEventListener('input', renderCart);
    }

    // 4. Attach Click & Keyboard Event Listeners to Product Cards (Event Delegation)
    const productsGrid = document.getElementById('posProductsGrid');
    if (productsGrid) {
        productsGrid.addEventListener('click', function (e) {
            const card = e.target.closest('.pos-product-card');
            if (!card) return;
            handleProductCardSelection(card);
        });

        productsGrid.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                const card = e.target.closest('.pos-product-card');
                if (card) {
                    e.preventDefault();
                    handleProductCardSelection(card);
                }
            }
        });
    }
});

/**
 * Handles adding a product to the cart from its DOM card element
 */
function handleProductCardSelection(card) {
    const id = parseInt(card.getAttribute('data-id'));
    const name = card.getAttribute('data-name');
    const price = parseFloat(card.getAttribute('data-price'));
    const stock = parseInt(card.getAttribute('data-stock'));
    const barcode = card.getAttribute('data-barcode') || '';
    const image = card.getAttribute('data-image') || '';

    addToCart(id, name, price, stock, barcode, image);
    showPOSToast(`Added '${name}' to cart`, 'info');
}

/**
 * Filter the visible products on the POS grid by name or category
 */
function filterProductGrid(keyword) {
    const term = (keyword || '').toLowerCase().trim();
    const activeCategory = document.querySelector('.category-pill.active')?.getAttribute('data-cat') || 'all';
    const cards = document.querySelectorAll('.pos-product-card');

    cards.forEach(card => {
        const name = (card.getAttribute('data-name') || '').toLowerCase();
        const barcode = (card.getAttribute('data-barcode') || '').toLowerCase();
        const cat = card.getAttribute('data-category') || '';

        const matchesText = !term || name.includes(term) || barcode.includes(term);
        const matchesCategory = (activeCategory === 'all') || (cat === activeCategory);

        if (matchesText && matchesCategory) {
            card.style.display = '';
        } else {
            card.style.display = 'none';
        }
    });
}

/**
 * Filter by Category Tab Pill
 */
function filterByCategory(categoryName, element) {
    document.querySelectorAll('.category-pill').forEach(el => el.classList.remove('active'));
    if (element) element.classList.add('active');

    const searchInput = document.getElementById('posSearchInput');
    filterProductGrid(searchInput ? searchInput.value : '');
}

/**
 * Adds product to cart by scanning its barcode
 */
function addProductByBarcode(barcode) {
    const cards = document.querySelectorAll('.pos-product-card');
    let foundCard = null;

    cards.forEach(card => {
        if (card.getAttribute('data-barcode') === barcode) {
            foundCard = card;
        }
    });

    if (foundCard) {
        const id = parseInt(foundCard.getAttribute('data-id'));
        const name = foundCard.getAttribute('data-name');
        const price = parseFloat(foundCard.getAttribute('data-price'));
        const stock = parseInt(foundCard.getAttribute('data-stock'));
        const image = foundCard.getAttribute('data-image') || '';

        addToCart(id, name, price, stock, barcode, image);
        showPOSToast(`Scanned: ${name}`, 'success');
    } else {
        showPOSToast(`Barcode not found: ${barcode}`, 'danger');
    }
}

/**
 * Adds an item to the shopping cart or increments quantity if already present
 */
function addToCart(id, name, price, maxStock, barcode, image) {
    const existingIndex = cart.findIndex(item => item.id === id);

    if (existingIndex > -1) {
        if (cart[existingIndex].quantity + 1 > maxStock) {
            alert(`Cannot add more. Current inventory stock limit for '${name}' is ${maxStock} units.`);
            return;
        }
        cart[existingIndex].quantity += 1;
    } else {
        if (maxStock <= 0) {
            alert(`'${name}' is currently out of stock.`);
            return;
        }
        cart.push({
            id: id,
            name: name,
            price: parseFloat(price),
            quantity: 1,
            maxStock: parseInt(maxStock),
            barcode: barcode || '',
            image: image || ''
        });
    }

    renderCart();
}

/**
 * Modifies quantity of an item in the cart
 */
function updateItemQuantity(id, delta) {
    const index = cart.findIndex(item => item.id === id);
    if (index > -1) {
        const newQty = cart[index].quantity + delta;
        if (newQty <= 0) {
            removeFromCart(id);
        } else if (newQty > cart[index].maxStock) {
            alert(`Stock limit reached. Maximum available: ${cart[index].maxStock} units.`);
        } else {
            cart[index].quantity = newQty;
            renderCart();
        }
    }
}

/**
 * Directly sets item quantity from text input
 */
function setItemQuantity(id, inputElem) {
    const index = cart.findIndex(item => item.id === id);
    if (index > -1) {
        let val = parseInt(inputElem.value);
        if (isNaN(val) || val <= 0) {
            val = 1;
        }
        if (val > cart[index].maxStock) {
            alert(`Maximum stock is ${cart[index].maxStock}. Adjusted to limit.`);
            val = cart[index].maxStock;
        }
        cart[index].quantity = val;
        renderCart();
    }
}

/**
 * Removes an item from the cart
 */
function removeFromCart(id) {
    cart = cart.filter(item => item.id !== id);
    renderCart();
}

/**
 * Clears the entire cart
 */
function clearCart() {
    if (cart.length === 0) return;
    if (confirm('Are you sure you want to clear the entire cart?')) {
        cart = [];
        renderCart();
    }
}

/**
 * Re-renders the cart table, line item subtotals, and overall order totals
 */
function renderCart() {
    const cartContainer = document.getElementById('cartItemsList');
    const emptyState = document.getElementById('cartEmptyState');
    const checkoutBtn = document.getElementById('btnProceedCheckout');
    const itemCountBadge = document.getElementById('cartItemCountBadge');

    let subtotal = 0.0;
    let totalItems = 0;

    if (!cartContainer) return;

    if (cart.length === 0) {
        cartContainer.innerHTML = '';
        if (emptyState) emptyState.style.display = 'block';
        if (checkoutBtn) checkoutBtn.disabled = true;
        if (itemCountBadge) itemCountBadge.innerText = '0 items';
    } else {
        if (emptyState) emptyState.style.display = 'none';
        if (checkoutBtn) checkoutBtn.disabled = false;

        let html = '';
        cart.forEach(item => {
            const lineTotal = item.price * item.quantity;
            subtotal += lineTotal;
            totalItems += item.quantity;

            html += `
                <div class="cart-item-row">
                    <div class="cart-item-info">
                        <div class="cart-item-title">${item.name}</div>
                        <div class="cart-item-sub">₱${item.price.toFixed(2)} each</div>
                    </div>
                    <div class="cart-item-controls">
                        <button type="button" class="btn-qty" onclick="updateItemQuantity(${item.id}, -1)">−</button>
                        <input type="number" class="qty-input" value="${item.quantity}" min="1" max="${item.maxStock}" onchange="setItemQuantity(${item.id}, this)">
                        <button type="button" class="btn-qty" onclick="updateItemQuantity(${item.id}, 1)">+</button>
                    </div>
                    <div class="cart-item-price">
                        ₱${lineTotal.toFixed(2)}
                    </div>
                    <button type="button" class="btn-remove-item" onclick="removeFromCart(${item.id})" title="Remove item">&times;</button>
                </div>
            `;
        });

        cartContainer.innerHTML = html;
        if (itemCountBadge) itemCountBadge.innerText = `${totalItems} ${totalItems === 1 ? 'item' : 'items'}`;
    }

    // Financial calculations
    const discountInput = document.getElementById('discountInput');
    const discount = discountInput ? (parseFloat(discountInput.value) || 0.0) : 0.0;
    const tax = roundToTwo(subtotal * TAX_RATE);
    let grandTotal = roundToTwo(subtotal + tax - discount);
    if (grandTotal < 0) grandTotal = 0.0;

    // Update DOM summary fields
    if (document.getElementById('cartSubtotalDisplay')) {
        document.getElementById('cartSubtotalDisplay').innerText = `₱${subtotal.toFixed(2)}`;
    }
    if (document.getElementById('cartTaxDisplay')) {
        document.getElementById('cartTaxDisplay').innerText = `₱${tax.toFixed(2)}`;
    }
    if (document.getElementById('cartGrandTotalDisplay')) {
        document.getElementById('cartGrandTotalDisplay').innerText = `₱${grandTotal.toFixed(2)}`;
    }

    // Update floating mobile cart bar
    const mobileBar = document.getElementById('posMobileCartBar');
    const mobileCount = document.getElementById('mobileCartCount');
    const mobileTotal = document.getElementById('mobileCartTotal');
    if (mobileBar && mobileCount && mobileTotal) {
        if (cart.length > 0) {
            mobileCount.innerText = `${totalItems} ${totalItems === 1 ? 'item' : 'items'}`;
            mobileTotal.innerText = `₱${grandTotal.toFixed(2)}`;
            mobileBar.classList.add('active');
        } else {
            mobileBar.classList.remove('active');
        }
    }

    // Update checkout modal fields if open
    const modalTotal = document.getElementById('modalTotalDueDisplay');
    if (modalTotal) {
        modalTotal.innerText = `₱${grandTotal.toFixed(2)}`;
    }

    updateChangeCalculation();
}

/**
 * Opens payment checkout modal
 */
function openCheckoutModal() {
    if (cart.length === 0) {
        alert('Cannot checkout with an empty cart.');
        return;
    }

    const discountInput = document.getElementById('discountInput');
    const discount = discountInput ? (parseFloat(discountInput.value) || 0.0) : 0.0;
    const subtotal = cart.reduce((acc, it) => acc + (it.price * it.quantity), 0);
    const tax = roundToTwo(subtotal * TAX_RATE);
    const totalDue = roundToTwo(subtotal + tax - discount);

    document.getElementById('modalTotalDueDisplay').innerText = `₱${totalDue.toFixed(2)}`;
    
    const cashInput = document.getElementById('amountTenderedInput');
    if (cashInput) {
        cashInput.value = '';
        cashInput.focus();
    }

    updateChangeCalculation();
    openModal('checkoutModal');
}

/**
 * Sets quick preset cash amount (e.g. Exact, ₱500, ₱1000)
 */
function setQuickCash(amount) {
    const cashInput = document.getElementById('amountTenderedInput');
    if (!cashInput) return;

    if (amount === 'exact') {
        const discountInput = document.getElementById('discountInput');
        const discount = discountInput ? (parseFloat(discountInput.value) || 0.0) : 0.0;
        const subtotal = cart.reduce((acc, it) => acc + (it.price * it.quantity), 0);
        const tax = roundToTwo(subtotal * TAX_RATE);
        const total = roundToTwo(subtotal + tax - discount);
        cashInput.value = total.toFixed(2);
    } else {
        cashInput.value = parseFloat(amount).toFixed(2);
    }

    updateChangeCalculation();
}

/**
 * Calculates customer change in real-time
 */
function updateChangeCalculation() {
    const cashInput = document.getElementById('amountTenderedInput');
    const changeBadge = document.getElementById('modalChangeDisplay');
    const completeBtn = document.getElementById('btnCompletePayment');
    const feedbackMsg = document.getElementById('paymentFeedbackMsg');

    if (!cashInput || !changeBadge) return;

    const tendered = parseFloat(cashInput.value) || 0.0;
    const discountInput = document.getElementById('discountInput');
    const discount = discountInput ? (parseFloat(discountInput.value) || 0.0) : 0.0;
    const subtotal = cart.reduce((acc, it) => acc + (it.price * it.quantity), 0);
    const tax = roundToTwo(subtotal * TAX_RATE);
    const totalDue = roundToTwo(subtotal + tax - discount);

    const change = tendered - totalDue;

    if (tendered >= totalDue && totalDue > 0) {
        changeBadge.innerText = `₱${change.toFixed(2)}`;
        changeBadge.className = 'change-badge badge-valid';
        if (feedbackMsg) feedbackMsg.innerText = 'Payment sufficient. Ready to process.';
        if (completeBtn) completeBtn.disabled = false;
    } else {
        changeBadge.innerText = 'Insufficient Cash';
        changeBadge.className = 'change-badge badge-invalid';
        if (feedbackMsg) {
            const needed = (totalDue - tendered).toFixed(2);
            feedbackMsg.innerText = tendered > 0 ? `Need ₱${needed} more to complete payment.` : 'Enter customer cash tendered.';
        }
        if (completeBtn) completeBtn.disabled = true;
    }
}

/**
 * Submits checkout transaction to Flask backend using ACID transaction
 */
async function submitCheckoutTransaction() {
    const cashInput = document.getElementById('amountTenderedInput');
    const discountInput = document.getElementById('discountInput');
    const paymentMethodSelect = document.getElementById('paymentMethodSelect');
    const completeBtn = document.getElementById('btnCompletePayment');

    const tendered = parseFloat(cashInput.value);
    const discount = discountInput ? (parseFloat(discountInput.value) || 0.0) : 0.0;
    const paymentMethod = paymentMethodSelect ? paymentMethodSelect.value : 'cash';

    if (isNaN(tendered) || tendered <= 0) {
        alert('Please enter a valid cash amount.');
        return;
    }

    if (cart.length === 0) {
        alert('Shopping cart is empty.');
        return;
    }

    const payload = {
        items: cart.map(it => ({
            product_id: it.id,
            quantity: it.quantity
        })),
        amount_tendered: tendered,
        discount_amount: discount,
        payment_method: paymentMethod
    };

    // Disable button and show spinner state
    if (completeBtn) {
        completeBtn.disabled = true;
        completeBtn.innerText = 'Processing Transaction...';
    }

    try {
        const response = await fetch('/pos/checkout', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok && result.success) {
            closeModal('checkoutModal');
            // Populate and show printable receipt
            showReceiptModal(result.receipt);
            // Reset cart
            cart = [];
            renderCart();
            // Refresh product cards stock displays on screen
            if (result.updated_stocks) {
                Object.keys(result.updated_stocks).forEach(pId => {
                    const card = document.querySelector(`.pos-product-card[data-id="${pId}"]`);
                    if (card) {
                        const newStock = result.updated_stocks[pId];
                        card.setAttribute('data-stock', newStock);
                        const stockLabel = card.querySelector('.product-stock-label');
                        if (stockLabel) {
                            stockLabel.innerText = `${newStock} in stock`;
                            if (newStock <= 5) stockLabel.className = 'product-stock-label stock-low';
                        }
                    }
                });
            }
        } else {
            alert(`Checkout Failed: ${result.error || 'Transaction could not be completed.'}`);
        }
    } catch (err) {
        console.error('Checkout network error:', err);
        alert(`Transaction Error: ${err.message || 'Server communication failure.'}`);
    } finally {
        if (completeBtn) {
            completeBtn.disabled = false;
            completeBtn.innerText = 'Complete Sale & Print Receipt';
        }
    }
}

/**
 * Renders the receipt inside the Receipt Modal
 */
function showReceiptModal(receipt) {
    if (!receipt) return;

    document.getElementById('receiptInvoiceNum').innerText = receipt.invoice_number;
    document.getElementById('receiptDateTime').innerText = receipt.created_at;
    document.getElementById('receiptCashier').innerText = receipt.cashier_name || 'Cashier';

    let itemsHtml = '';
    receipt.items.forEach(it => {
        itemsHtml += `
            <tr>
                <td style="text-align: left;">
                    <div style="font-weight: 700; color: #111;">${it.name}</div>
                    <div style="font-size: 0.75rem; color: #666; margin-top: 0.15rem;">${it.barcode || ''}</div>
                </td>
                <td style="text-align: center; vertical-align: top;">${it.quantity}</td>
                <td style="text-align: right; vertical-align: top;">₱${parseFloat(it.unit_price).toFixed(2)}</td>
                <td style="text-align: right; vertical-align: top; font-weight: 600;">₱${parseFloat(it.subtotal).toFixed(2)}</td>
            </tr>
        `;
    });

    document.getElementById('receiptItemsBody').innerHTML = itemsHtml;
    document.getElementById('receiptSubtotal').innerText = `₱${parseFloat(receipt.subtotal).toFixed(2)}`;
    document.getElementById('receiptTax').innerText = `₱${parseFloat(receipt.tax_amount).toFixed(2)}`;
    document.getElementById('receiptDiscount').innerText = `₱${parseFloat(receipt.discount_amount).toFixed(2)}`;
    document.getElementById('receiptTotal').innerText = `₱${parseFloat(receipt.total_amount).toFixed(2)}`;
    document.getElementById('receiptTendered').innerText = `₱${parseFloat(receipt.amount_tendered).toFixed(2)}`;
    document.getElementById('receiptChange').innerText = `₱${parseFloat(receipt.change_amount).toFixed(2)}`;

    // Set print link for direct printing
    const printLink = document.getElementById('receiptPrintLink');
    if (printLink) {
        printLink.href = `/receipt/${receipt.sale_id}/print`;
    }

    openModal('receiptModal');
}

/**
 * Triggers standard browser window print for the receipt area
 */
function printCurrentReceipt() {
    window.print();
}

/**
 * Little floating toast message for scanner confirmation
 */
function showPOSToast(msg, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `pos-toast toast-${type}`;
    toast.innerText = msg;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 400);
    }, 2500);
}

function roundToTwo(num) {
    return +(Math.round(num + "e+2") + "e-2");
}
