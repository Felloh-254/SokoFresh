$(document).ready(function () {

    loadFarmerProductTypes();
    
    // Listener for the signup form
    $("#signup-form").on("submit", function (e) {
        e.preventDefault();

        const formData = {
            user_email: $("#user_email").val(),
            user_name: $("#user_name").val(),
            user_dob: $("#user_dob").val(),
            user_contact: $("#user_contact").val(),
            user_password: $("#user_password").val(),
            user_confirm_password: $("#user_confirm_password").val()
        };


        $.ajax({
            url: "/signup",
            method: "POST",
            contentType: "application/json",
            data: JSON.stringify(formData),
            success: function (response) {
                window.location.href = response.redirect_url + '?email=' + encodeURIComponent(response.user_email);
            },
            error: function (xhr, status, error) {
    	        const res = JSON.parse(xhr.responseText);
                showFlashMessage(res.message, 'error');
            }
        });
    });

    $("#login-form").on("submit", function (e) {
        e.preventDefault();

        const formData = {
            user_email: $("#user_email").val(),
            user_password: $("#user_password").val(),
        };

        $.ajax({
            url: "/login",
            method: "POST",
            contentType: "application/json",
            data: JSON.stringify(formData),
            success: function (response) {
                window.location.href = response.redirect_url;
            },
            error: function (xhr, status, error) {
                const res = JSON.parse(xhr.responseText);
                showFlashMessage(res.message, 'error');
            }
        });
    });



    // Listener fo account deletion trigger
    $('#delete-account-btn').on('click', function() {
        // Confirm whether the user wants to delete the account
        const deletion_reason = document.getElementById('deletion-reason').value;
        if (confirm("Are you sure you want to proceed deleting your account??")) {
            // Proceed with deletion
            $.ajax({
                url: "/settings/delete-account",
                method: "POST",
                contentType: "application/json",
                data:{"deletion_reason": deletion_reason},
                success: function(response) {
                    // Redirect to logout after successful account deletion
                    showFlashMessage(response.message);
                    window.location.href = response.redirect_url;
                },
                error: function (xhr, status, error) {
                    const res = JSON.parse(xhr.responseText);
                    showFlashMessage(res.message, 'error');
                }
            });
        }
    });

    

    // Listener for updating produce types based on their category
    $('#produce_category, #update_produce_category').on('change', function () {
        if (window.initializing) return;

        const selected = $(this).val()?.map(Number) || [];
        const targetId = this.id === 'produce_category' ? 'produce_types' : 'update_produce_types';
        const typeSelect = document.getElementById(targetId);

        const previouslySelected = Array.from(typeSelect.selectedOptions).map(opt => opt.value);

        fetch('/api/product-types', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ category_ids: selected })
        })
        .then(res => res.json())
        .then(data => {
            typeSelect.innerHTML = "";

            data.forEach(type => {
                const option = document.createElement('option');
                option.value = type.id;
                option.textContent = type.name;

                if (previouslySelected.includes(type.name)) {
                    option.selected = true;
                }

                typeSelect.appendChild(option);
            });

            $(`#${targetId}`).trigger('change.select2');
        })
        .catch(err => {
            console.error("Error fetching product types:", err);
        });
    });

    // Listener for changing user's role
    $('#changeRoleModalForm').on('submit', function(e) {
        e.preventDefault();

        // Creating formdata from the actual modal form
        const form = document.getElementById('changeRoleModalForm');
        const formData = new FormData(form);

        $.ajax({
            url: '/start-selling',
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function (response) {
                location.reload();
                showFlashMessage(response.message);
            },
            error: function (xhr) {
                const res = JSON.parse(xhr.responseText);
                showFlashMessage(res.message || 'An error occurred', 'error');
            }
        });
    });

    // Listener for posting a product
    $('#post-product-form').on('submit', function (e) {
        e.preventDefault();

        // Create a new formData
        const form = document.getElementById('post-product-form');
        const formData = new FormData(form)

        $.ajax({
            url: '/farmer/post-product',
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function (response) {
                showFlashMessage(response.message);
                location.reload()
            },
            error: function (xhr) {
                const res = JSON.parse(xhr.responseText);
                showFlashMessage(res.message || "An error occurred", "error");
            }
        })
    });

    // Listener for updating farm details
    $('#updateFarmModalForm').on('submit', function(e) {
        e.preventDefault();
        
        // Get the actual selected values from the produce types select
        const produceTypesSelect = document.getElementById('update_produce_types');
        const selectedProduceTypes = Array.from(produceTypesSelect.selectedOptions).map(option => option.value);
        
        
        // Creating formdata from the actual modal form
        const form = document.getElementById('updateFarmModalForm');
        const formData = new FormData(form);
        
        $.ajax({
            url: '/farmer/update-farm-details',
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function (response) {
                // location.reload();
                showFlashMessage(response.message);
            },
            error: function (xhr) {
                const res = JSON.parse(xhr.responseText);
                showFlashMessage(res.message || 'An error occurred', 'error');
            }
        });
    });


    function showFlashMessage(message, type) {
        const flashMessage = document.createElement('div');
        flashMessage.textContent = message;

        const styles = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            padding: 10px 20px;
            border-radius: 5px;
            color: white;
            font-weight: bold;
            z-index: 9999;
        `;

        switch (type) {
            case 'success':
                flashMessage.style.backgroundColor = 'green';
                break;
            case 'error':
                flashMessage.style.backgroundColor = 'red';
                break;
            case 'info':
                flashMessage.style.backgroundColor = 'blue';
                break;
            case 'warning':
                flashMessage.style.backgroundColor = 'orange';
                break;
            default:
                flashMessage.style.backgroundColor = 'gray';
                break;
        }

        flashMessage.style.cssText += styles;
        document.body.appendChild(flashMessage);
        setTimeout(() => {
            flashMessage.remove();
        }, 3000);
    }

    $('.select2').select2({
        tags: false,
        placeholder: "Select options",
        allowClear: true
    });

    $('#product_type_id, #product_unit').select2({
        placeholder: "Select a product type",
        width: '100%',
        maximumSelectionLength: 1,
        allowClear: true
    });
});

// Function to load the user product types
function loadFarmerProductTypes() {
    fetch('/api/my-product-types', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(res => res.json())
    .then(data => {
        const typeSelect = $('#product_type_id');
        typeSelect.empty();

        typeSelect.append('<option value="">Select a product type</option>');
        data.forEach(type => {
            typeSelect.append( `<option value="${type.product_id}">${type.name_en} / ${type.name_sw} / ${type.name_local}</option>`);
        });

        $('#product_type_id').trigger('change.select2');
    })
    .catch(err => {
        console.error("Error fetching product types:", err);
    });
}


function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}


// Listener for liking a product
function toggleLike(productId, btn) {
    fetch(`/marketplace/like/${productId}`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrf_token'),
            'Content-Type': 'application/json'
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            const icon = btn.querySelector('i');
            if (data.action === 'liked') {
                icon.classList.add('text-danger');
            } else {
                icon.classList.remove('text-danger');
            }
        } else {
            alert('Error: ' + data.message);
        }
    })
    .catch(err => {
        console.error('Like failed:', err);
    });
}

function isUserLoggedIn() {
    const meta = document.querySelector('meta[name="user-authenticated"]');
    return meta && meta.content === 'true';
}


const cart = window.userCart || {};
console.log(cart); 

updateCartDisplay();

// Updating the display of the cart
function updateCartDisplay() {
    const cartItemsContainer = document.getElementById('cartItems');
    const cartCount = document.querySelector('.cart-count');
    const cartTotalDisplay = document.getElementById('cartTotal');
    const cartTotalSummary = document.getElementById('cartTotalSummary');

    cartItemsContainer.innerHTML = '';
    let totalItems = 0;
    let totalCost = 0;

    // Use proper array iteration
    cart.forEach(item => {
        if (!item || !item.cart_item_product_id) return; // Skip invalid items
        
        const productId = item.cart_item_product_id;
        const qty = item.cart_item_product_quantity;
        const price = item.product_unit_price;
        const name = item.product_name;

        totalItems += qty;
        totalCost += qty * price;

        const div = document.createElement('div');
        div.className = 'cart-item';
        div.innerHTML = `
            <div>
                <strong>${name}</strong><br>
                <small>${qty} × Ksh ${price} = Ksh ${(qty * price).toFixed(2)}</small>
            </div>
            <div>
                <button onclick="changeQty(${productId}, -1)">−</button>
                <span>${qty}</span>
                <button onclick="changeQty(${productId}, 1)">+</button>
                <button onclick="removeFromCart(${productId})"><i class="fa fa-trash"></i></button>
            </div>
        `;
        cartItemsContainer.appendChild(div);
    });

    cartCount.textContent = totalItems;
    const formattedTotal = `Ksh ${totalCost.toFixed(2)}`;
    cartTotalDisplay.textContent = formattedTotal;
    cartTotalSummary.textContent = formattedTotal;
}


function addToCartFromModal() {
    const productId = window.currentProductId;
    const availableQty = window.currentProductQty;
    const customQty = parseInt(document.getElementById('mpQtyInput')?.value || '1');

    addToCart(productId, availableQty, customQty);
}


// Function to change the quantity of products in the cart
function changeQty(productId, delta) {
    const item = cart.find(item => item.cart_item_product_id === productId);
    if (!item) return;

    let newQty = item.cart_item_product_quantity + delta;

    if (newQty < 1) {
        if (confirm("Remove this item from your cart?")) {
            removeFromCart(productId);
        }
        return;
    }

    // Update local cart first
    item.cart_item_product_quantity = newQty;
    updateCartDisplay();

    // Send the new absolute quantity with set_absolute flag
    fetch('/marketplace/cart/add', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrf_token')
        },
        body: JSON.stringify({
            product_id: productId,
            quantity: newQty,
            set_absolute: true  // Tell backend to set absolute quantity
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status !== 'success') {
            alert('Failed to update cart: ' + data.message);
            // Revert local changes on failure
            item.cart_item_product_quantity -= delta;
            updateCartDisplay();
        }
    })
    .catch(err => {
        console.error('Error updating cart:', err);
        // Revert local changes on failure
        item.cart_item_product_quantity -= delta;
        updateCartDisplay();
    });
}

// Adding products to cart
function addToCart(productId, availableQty, customQty = null, button = null) {
    const input = document.getElementById('mpQtyInput');
    const inputQty = input ? parseInt(input.value) : 1;

    let existingItem = cart.find(item => item.cart_item_product_id === productId);
    let currentQty = existingItem ? existingItem.cart_item_product_quantity : 0;

    let newQty = customQty !== null
        ? customQty
        : (currentQty === 0 && inputQty > 0 ? inputQty : currentQty + 1);

    if (newQty > availableQty) {
        alert('No more stock available');
        return;
    }

    if (newQty <= 0) {
        removeFromCart(productId);
        updateCartDisplay();
        return;
    }

    // Get product name and price
    let name = '';
    let unitPrice = 0;

    if (button) {
        // Coming from product grid
        const productCard = button.closest('.product-card');
        name = productCard.querySelector('.product-name')?.textContent.trim() || '';
        unitPrice = parseFloat(
            productCard.querySelector('[data-price]')?.getAttribute('data-price') || '0'
        );
    } else {
        // Coming from modal
        name = document.getElementById('mpProductName')?.textContent.trim() || '';
        const priceStr = document.getElementById('mpProductPrice')?.textContent || '';
        unitPrice = parseFloat(priceStr.replace(/[^\d.]/g, '')) || 0;
    }

    const itemData = {
        cart_item_product_id: productId,
        cart_item_user_id: window.userId,
        product_name: name,
        cart_item_product_quantity: newQty,
        product_unit_price: unitPrice
    };

    // Determine if this is setting absolute quantity or adding
    const isAbsolute = customQty !== null;
    const quantityToSend = isAbsolute ? newQty : (existingItem ? 1 : inputQty);
    
    fetch('/marketplace/cart/add', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrf_token')
        },
        body: JSON.stringify({
            product_id: productId,
            quantity: quantityToSend,
            set_absolute: isAbsolute
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            const existingIndex = cart.findIndex(item => item.cart_item_product_id === productId);
            if (existingIndex !== -1) {
                cart[existingIndex] = itemData;
            } else {
                cart.push(itemData);
            }
            updateCartDisplay();
        } else {
            alert('Failed to add to cart: ' + data.message);
        }
    });
}



// Remove item from cart
function removeFromCart(productId) {
    if (!confirm('Are you sure you want to remove this item from your cart?')) {
        return;
    }

    fetch('/marketplace/cart/add', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrf_token')
        },
        body: JSON.stringify({
            product_id: productId,
            quantity: 0
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            // Remove from local cart array
            const itemIndex = cart.findIndex(item => item.cart_item_product_id === productId);
            if (itemIndex !== -1) {
                cart.splice(itemIndex, 1);
            }
            
            // Update the display
            updateCartDisplay();            
        } else {
            alert('Failed to remove item from cart: ' + data.message);
        }
    })
    .catch(err => {
        console.error('Error removing item from cart:', err);
        alert('Something went wrong removing the item from cart.');
    });
}



// Removing from cart
function checkoutCart() {
    // Check if user is logged in
    if (!isUserLoggedIn()) {
        alert('You need to log in before placing an order.');
        window.location.href = '/login?next=/marketplace';
        return;
    }

    // Check if cart has items
    if (cart.length === 0) {
        alert('Your cart is empty.');
        return;
    }

    // Get drop location
    const dropLocationSelect = document.getElementById('buyer-drop-location');
    const dropLocation = dropLocationSelect?.value?.trim();

    if (!dropLocation) {
        alert('Please select a drop location.');
        return;
    }

    // Get payment method
    const paymentMethodInput = document.querySelector('input[name="payment-method"]:checked');
    const paymentMethod = paymentMethodInput?.value?.trim();

    if (!paymentMethod) {
        alert('Please select a payment method.');
        return;
    }

    // Prepare data to send
    const cartItems = Array.from(cart).filter(item => item && item.cart_item_product_id);
    
    const payload = {
        cart_items: cartItems,
        drop_location: dropLocation,
        payment_method: paymentMethod
    };


    // Send data to database
    fetch('/marketplace/place-order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrf_token')
        },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        console.log('Backend response:', data);
        if (data.status === 'success') {
            alert('Order placed successfully!');
            cart.length = 0;
            updateCartDisplay();
        } else {
            alert(`Order failed: ${data.message}`);
        }
    })
    .catch(err => {
        console.error('Order placement error:', err);
        alert('Something went wrong placing the order.');
    });
}