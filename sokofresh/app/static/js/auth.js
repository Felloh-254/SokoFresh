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

    

    // Listener for updating produce types based on their category

    // keep this listener for change events in the select2
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


let cart = JSON.parse(localStorage.getItem('cart')) || {};

// Updating the display of the cart
function updateCartDisplay() {
    const cartItemsContainer = document.getElementById('cartItems');
    const cartCount = document.querySelector('.cart-count');
    const cartTotalDisplay = document.getElementById('cartTotal');

    cartItemsContainer.innerHTML = '';

    let totalItems = 0;
    let totalCost = 0;

    for (const productId in cart) {
        const item = cart[productId];
        totalItems += item.quantity;
        totalCost += item.quantity * item.unit_price;

        // Add to DOM
        const div = document.createElement('div');
        div.className = 'cart-item';
        div.innerHTML = `
            <strong>${item.name}</strong><br>
            ${item.quantity} × Ksh ${item.unit_price.toFixed(2)} = Ksh ${(item.quantity * item.unit_price).toFixed(2)}
        `;
        cartItemsContainer.appendChild(div);
    }

    cartCount.textContent = totalItems;
    cartTotalDisplay.textContent = `Ksh ${totalCost.toFixed(2)}`;
}



// Adding products to cart
function addToCart(productId, availableQty) {
    const input = document.getElementById('mpQtyInput');
    const currentQty = productQuantities[productId] || 0;
    const inputQty = input ? parseInt(input.value) : 0;
    const newQty = currentQty === 0 && inputQty > 0 ? inputQty : currentQty + 1;

    if (newQty > availableQty) {
        alert('No more stock available');
        return;
    }

    // Save quantity
    productQuantities[productId] = newQty;

    // Grab other product info
    const name = document.getElementById('mpProductName')?.textContent || 'Product';
    const priceStr = document.getElementById('mpProductPrice')?.textContent || 'KES 0';
    const unitPrice = parseFloat(priceStr.replace(/[^\d.]/g, '')) || 0;

    cart[productId] = {
        product_id: productId,
        name: name,
        quantity: newQty,
        unit_price: unitPrice
    };

    localStorage.setItem('cart', JSON.stringify(cart));

    updateCartDisplay();

    alert(`Added ${name} (x${newQty}) to cart!`);
}


// Placing an order
function checkoutCart() {
    const cart = JSON.parse(localStorage.getItem('cart')) || {};

    if (!isUserLoggedIn()) {
        alert('You need to log in before placing an order.');
        window.location.href = '/login?next=/marketplace';
        return;
    }

    if (Object.keys(cart).length === 0) {
        alert('Your cart is empty.');
        return;
    }

    // 🔽 Get drop location
    const dropLocationSelect = document.getElementById('buyer-drop-location');
    const dropLocation = dropLocationSelect ? dropLocationSelect.value : '';

    // 🔽 Get selected payment method
    const paymentMethodInput = document.querySelector('input[name="payment-method"]:checked');
    const paymentMethod = paymentMethodInput ? paymentMethodInput.value : '';

    // Validate both
    if (!dropLocation) {
        alert('Please select a drop location.');
        return;
    }

    if (!paymentMethod) {
        alert('Please select a payment method.');
        return;
    }

    const payload = {
        cart_items: Object.values(cart),
        drop_location: dropLocation,
        payment_method: paymentMethod
    };

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
        if (data.status === 'success') {
            alert('Order placed successfully!');
            localStorage.removeItem('cart');
            productQuantities = {};
            updateCartDisplay();
            window.location.href = '/orders'; // or thank-you page
        } else {
            alert(`Order failed: ${data.message}`);
        }
    })
    .catch(err => {
        console.error('Order placement error:', err);
        alert('Something went wrong placing the order.');
    });
}