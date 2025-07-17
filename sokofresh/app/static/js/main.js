document.addEventListener('DOMContentLoaded', () => {
    // Listener For Uploading Product Image
    const fileInput = document.getElementById('product_image');
    const uploadArea = document.getElementById('uploadArea');
    const imagePreview = document.getElementById('imagePreview');
    const previewImage = document.getElementById('previewImage');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const changeImageBtn = document.getElementById('changeImage');
    const removeImageBtn = document.getElementById('removeImage');
    const uploadContainer = document.getElementById('imageUploadContainer');
    const progressBar = document.getElementById('progressBar');
    const uploadProgress = document.getElementById('uploadProgress');

    // Handle file selection
    if (fileInput && changeImageBtn && removeImageBtn && uploadArea) {
        fileInput.addEventListener('change', handleFileSelect);
        changeImageBtn.addEventListener('click', () => fileInput.click());
        removeImageBtn.addEventListener('click', removeImage);

        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('drag-over');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('drag-over');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFile(files[0]);
            }
        });
    }

    function handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) {
            handleFile(file);
        }
    }

    function handleFile(file) {
        // Validate file type
        if (!file.type.startsWith('image/')) {
            alert('Please select a valid image file.');
            return;
        }

        // Validate file size (5MB limit)
        if (file.size > 5 * 1024 * 1024) {
            alert('File size must be less than 5MB.');
            return;
        }

        // Show progress
        showProgress();

        // Create file reader
        const reader = new FileReader();
        reader.onload = (e) => {
            // Simulate upload progress
            simulateProgress(() => {
                showPreview(e.target.result, file);
            });
        };
        reader.readAsDataURL(file);
    }

    function showProgress() {
        uploadProgress.style.display = 'block';
    }

    function simulateProgress(callback) {
        let progress = 0;
        const interval = setInterval(() => {
            progress += Math.random() * 30;
            if (progress >= 100) {
                progress = 100;
                clearInterval(interval);
                setTimeout(() => {
                    uploadProgress.style.display = 'none';
                    callback();
                }, 300);
            }
            progressBar.style.width = progress + '%';
        }, 100);
    }

    function showPreview(src, file) {
        previewImage.src = src;
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        
        uploadArea.style.display = 'none';
        imagePreview.classList.add('show');
        uploadContainer.classList.add('has-image');
    }

    function removeImage() {
        fileInput.value = '';
        previewImage.src = '';
        fileName.textContent = '';
        fileSize.textContent = '';
        
        uploadArea.style.display = 'block';
        imagePreview.classList.remove('show');
        uploadContainer.classList.remove('has-image');
        progressBar.style.width = '0%';
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }


    // Listener For Cropping Profile Picture
    const profileFileInput = document.getElementById('user_profile_pic');
    const preview = document.getElementById('updatedProfilePicPreview');
    const form = document.getElementById('updateModalForm');
    const submitBtn = document.getElementById('updateProfileSubmitBtn');

    let cropper;

    if (profileFileInput && preview && form && submitBtn) {
        profileFileInput.addEventListener('change', function (e) {
            const file = e.target.files[0];
            if (file && file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = function (event) {
                    preview.src = event.target.result;

                    if (cropper) cropper.destroy();
                    cropper = new Cropper(preview, {
                        aspectRatio: 1,
                        viewMode: 1,
                        autoCropArea: 1,
                    });
                };
                reader.readAsDataURL(file);
            }
        });

        submitBtn.addEventListener('click', function (e) {
            e.preventDefault();

            // If cropping is active, use cropped image
            if (cropper) {
                cropper.getCroppedCanvas({
                    width: 300,
                    height: 300
                }).toBlob(function (blob) {
                    const username = document.getElementById('user_full_name').value
                        .trim()
                        .replace(/\s+/g, '_')
                        .toLowerCase();
                    const timestamp = Date.now();
                    const filename = `${username}_${timestamp}.png`;

                    const newFile = new File([blob], filename, { type: 'image/png' });

                    const formData = new FormData(form);
                    formData.set('user_profile_pic', newFile); // Replace the original file

                    fetch(form.action, {
                        method: 'POST',
                        body: formData,
                    })
                    .then(response => response.json())
                    .then(data => {
                        showFlashMessage(data.message || 'Profile updated!', 'success');
                        location.reload();
                    })
                    .catch(error => {
                        console.error('Upload failed:', error);
                        alert('Error uploading profile');
                    });
                });
            } else {
                // No cropping: send original formData
                const formData = new FormData(form);
                fetch(form.action, {
                    method: 'POST',
                    body: formData,
                })
                .then(response => response.json())
                .then(data => {
                    showFlashMessage(data.message || 'Profile updated!', 'success');
                    location.reload();
                })
                .catch(error => {
                    console.error('Upload failed:', error);
                    alert('Error uploading profile');
                });
            }
        });
    }

    let map;
    let marker;
    let userEdited = false;
    const locationInput = document.getElementById('farm_location');

    if (locationInput) {
        locationInput.addEventListener('input', () => {
            userEdited = true;
        });
    }

    function reverseGeocode(lat, lng) {
        if (userEdited) return;
        const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}`;

        fetch(url)
            .then(res => res.json())
            .then(data => {
                console.log("Reverse geocoding data:", data);

                const locationInput = document.getElementById('farm_location');

                if (data && data.address) {
                    const { suburb, village, town, city, county, state, country } = data.address;
                    locationInput.value = suburb || village || town || city || county || state || country || 'Unknown location';
                } else {
                    locationInput.value = 'Unknown location';
                }
            })
            .catch(err => {
                console.error("Geocoding failed:", err);
                document.getElementById('farm_location').value = 'Unknown location';
            });
    }

    function initMap(lat = -1.286389, lng = 36.817223) {
        map = L.map('map').setView([lat, lng], 13);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19
        }).addTo(map);

        marker = L.marker([lat, lng]).addTo(map);

        // Save coordinates to hidden fields
        document.getElementById('farm_latitude').value = lat.toFixed(6);
        document.getElementById('farm_longitude').value = lng.toFixed(6);

        // Reverse geocode initial location
        reverseGeocode(lat, lng);

        // Update marker and reverse geocode on map click
        map.on('click', function (e) {
            const selectedLat = e.latlng.lat.toFixed(6);
            const selectedLng = e.latlng.lng.toFixed(6);

            marker.setLatLng(e.latlng);

            document.getElementById('farm_latitude').value = selectedLat;
            document.getElementById('farm_longitude').value = selectedLng;

            reverseGeocode(selectedLat, selectedLng);
        });
    }

    // Center map using user's location or default
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const userLat = position.coords.latitude;
                const userLng = position.coords.longitude;
                initMap(userLat, userLng); // user's actual location
            },
            () => {
                initMap(); // fallback to default (Nairobi)
            }
        );
    } else {
        initMap(); // fallback if geolocation not supported
    }


    window.initializing = true;

    const requiredIds = [
        'update_farm_size',
        'update_produce_category',
        'update_produce_types',
        'update_farming_methods',
        'update_availability_schedule',
        'update_mpesa_number',
        'update_transport',
        'update_storage'
    ];

    const allPresent = requiredIds.every(id => document.getElementById(id));

    if (allPresent) {
        fetch('/api/get-farmer-details', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(res => res.json())
        .then(data => {            
            document.getElementById('update_farm_size').value = data.farm_size || '';
            document.getElementById('update_mpesa_number').value = data.mpesa_number || '';

            function setSelectedOptionsByText(selectId, selectedTexts = []) {
                const select = document.getElementById(selectId);
                Array.from(select.options).forEach(opt => {
                    opt.selected = selectedTexts.includes(opt.text.trim());
                });
                $(`#${selectId}`).trigger('change');
            }

            // Set selected categories by text
            setSelectedOptionsByText('update_produce_category', data.category_name_en);

            const produceTypesField = document.getElementById('update_produce_types');

            // Clear existing options first
            produceTypesField.innerHTML = '';

            // Handle produce types - check if farmer has any existing produce types
            if (data.produce_name_en && data.produce_types && 
                data.produce_name_en.length > 0 && data.produce_types.length > 0 &&
                data.produce_name_en.length === data.produce_types.length) {
                
                for (let i = 0; i < data.produce_name_en.length; i++) {
                    const opt = document.createElement('option');
                    opt.value = data.produce_types[i]; // ID as value
                    opt.textContent = data.produce_name_en[i]; // Name as display text
                    opt.selected = true; // Pre-select current produce types
                    produceTypesField.appendChild(opt);
                }
                
                // Trigger change event for select2 after adding options
                $('#update_produce_types').trigger('change');
                
            } else {
                console.log("No existing produce types found or empty arrays", {
                    produce_names: data.produce_name_en,
                    produce_types: data.produce_types,
                    names_length: data.produce_name_en?.length,
                    types_length: data.produce_types?.length
                });
            }

            // Set other fields
            setSelectedOptionsByText('update_farming_methods', data.produce_farming_methods);
            setSelectedOptionsByText('update_availability_schedule', data.produce_availability);

            document.getElementById('update_transport').checked = data.transport === true || data.transport === 'true';
            document.getElementById('update_storage').checked = data.storage === true || data.storage === 'true';

            // Now enable category-change fetching
            window.initializing = false;
        })
        .catch(error => {
            console.error('Error fetching farmer details:', error);
        });
    }

    // Chat box functionality
    document.getElementById('openChatBtn').addEventListener('click', function () {
        document.getElementById('chatBox').classList.remove('hidden');
    });
    
    document.getElementById('closeChatBtn').addEventListener('click', function () {
        document.getElementById('chatBox').classList.add('hidden');
    });

    // Scroll to top functionality
    document.getElementById('scrollToTopBtn').addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // Show/hide scroll to top button based on scroll position
    window.addEventListener('scroll', function() {
        const scrollBtn = document.getElementById('scrollToTopBtn');
        if (window.pageYOffset > 300) {
            scrollBtn.style.display = 'block';
        } else {
            scrollBtn.style.display = 'none';
        }
    });

    // Close chat box when clicking outside of it
    document.addEventListener('click', function(event) {
        const chatBox = document.getElementById('chatBox');
        const openBtn = document.getElementById('openChatBtn');
        
        if (!chatBox.contains(event.target) && !openBtn.contains(event.target)) {
            chatBox.classList.add('hidden');
        }
    });


    // Search and Filter functionality for orders
    const orderSearchInput = document.getElementById('searchInput');
    const orderStatusFilter = document.getElementById('statusFilter');
    const orderDateFilter = document.getElementById('dateFilter');
    const ordersList = document.getElementById('ordersList');

        
    if (orderSearchInput && orderStatusFilter && orderDateFilter && ordersList) {
        function filterOrders() {
            const searchTerm = orderSearchInput.value.toLowerCase();
            const statusValue = orderStatusFilter.value;
            const orders = ordersList.querySelectorAll('.order-card');

            orders.forEach(order => {
                const orderText = order.textContent.toLowerCase();
                const orderStatus = order.getAttribute('data-status');

                const matchesSearch = orderText.includes(searchTerm);
                const matchesStatus = !statusValue || orderStatus === statusValue;

                if (matchesSearch && matchesStatus) {
                    order.style.display = 'block';
                } else {
                    order.style.display = 'none';
                }
            });
        }

        orderSearchInput.addEventListener('input', filterOrders);
        orderStatusFilter.addEventListener('change', filterOrders);

        // Update order status
        function updateOrderStatus(button, newStatus) {
            const orderCard = button.closest('.order-card');
            const statusBadge = orderCard.querySelector('.status-badge');
            const actionsDiv = orderCard.querySelector('.order-actions');
            
            // Update status attribute
            orderCard.setAttribute('data-status', newStatus);
            
            // Update status badge
            statusBadge.className = `status-badge status-${newStatus}`;
            
            const statusTexts = {
                'processing': 'Processing',
                'ready': 'Ready for Pickup',
                'completed': 'Completed',
                'cancelled': 'Cancelled'
            };
            
            statusBadge.textContent = statusTexts[newStatus] || 'Unknown';
            
            // Update action buttons based on new status
            let newButtons = '';
            
            switch(newStatus) {
                case 'processing':
                    newButtons = `
                        <button class="btn btn-ready" onclick="updateOrderStatus(this, 'ready')">Mark Ready</button>
                        <button class="btn btn-cancel" onclick="updateOrderStatus(this, 'cancelled')">Cancel</button>
                        <button class="btn btn-view">View Details</button>
                    `;
                    break;
                case 'ready':
                    newButtons = `
                        <button class="btn btn-complete" onclick="updateOrderStatus(this, 'completed')">Mark Complete</button>
                        <button class="btn btn-view">View Details</button>
                    `;
                    break;
                case 'completed':
                    newButtons = `
                        <button class="btn btn-view">View Receipt</button>
                    `;
                    break;
                case 'cancelled':
                    newButtons = `
                        <button class="btn btn-view">View Details</button>
                    `;
                    statusBadge.className = 'status-badge status-cancelled';
                    break;
            }
            
            actionsDiv.innerHTML = newButtons;
            
            // Update stats (simple increment/decrement)
            updateStats();
            
            // Show confirmation
            const confirmationMessages = {
                'processing': 'Order accepted and moved to processing!',
                'ready': 'Order marked as ready for pickup!',
                'completed': 'Order completed successfully!',
                'cancelled': 'Order cancelled.'
            };
            
            alert(confirmationMessages[newStatus]);
        }

        // Update stats counters (simplified)
        function updateStats() {
            const orders = document.querySelectorAll('.order-card');
            const stats = {
                'new': 0,
                'processing': 0,
                'ready': 0,
                'completed': 0
            };

            orders.forEach(order => {
                const status = order.getAttribute('data-status');
                if (stats.hasOwnProperty(status)) {
                    stats[status]++;
                }
            });

            // Update stat displays
            document.querySelector('.stat-new').textContent = stats.new;
            document.querySelector('.stat-processing').textContent = stats.processing;
            document.querySelector('.stat-ready').textContent = stats.ready;
            document.querySelector('.stat-completed').textContent = stats.completed;
        }

        // Initialize stats on page load
        updateStats();

        // Handle view details/receipt buttons
        document.addEventListener('click', function(e) {
            if (e.target.textContent === 'View Details' || e.target.textContent === 'View Receipt') {
                const orderCard = e.target.closest('.order-card');
                const orderId = orderCard.querySelector('h3').textContent;
                alert(`Opening detailed view for ${orderId}`);
            }
        });
    }

    // Search and Filter functionality for listings 
    const listingSearchInput = document.getElementById('listingSearchInput');
    const listingStatusFilter = document.getElementById('listingStatusFilter');
    const listingCategoryFilter = document.getElementById('listingCategoryFilter');
    const listingsGrid = document.getElementById('listingsGrid');

    if (listingSearchInput && listingStatusFilter && listingCategoryFilter && listingsGrid) {
        // Displaying the search results based on what is typed
        function filterListings() {
            const searchTerm = listingSearchInput.value.toLowerCase();
            const statusValue = listingStatusFilter.value;
            const categoryValue = listingCategoryFilter.value;
            const cards = listingsGrid.querySelectorAll('.listing-card');

            cards.forEach(card => {
                const productName = card.querySelector('.listing-product-name').textContent.toLowerCase();
                const cardStatus = card.getAttribute('data-status');
                const cardCategory = card.getAttribute('data-category');

                const matchesSearch = productName.includes(searchTerm);
                const matchesStatus = !statusValue || cardStatus === statusValue;
                const matchesCategory = !categoryValue || cardCategory === categoryValue;

                if (matchesSearch && matchesStatus && matchesCategory) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }

        listingSearchInput.addEventListener('input', filterListings);
        listingStatusFilter.addEventListener('change', filterListings);
        listingCategoryFilter.addEventListener('change', filterListings);

        // Update card action buttons for farmer product listings
        document.addEventListener('click', function(e) {
            if (e.target.classList.contains('listing-btn-edit')) {
                let button = e.target;

                document.getElementById('edit_name').value = button.dataset.name || '';
                document.getElementById('edit_quantity').value = button.dataset.qty || '';
                document.getElementById('edit_price').value = button.dataset.price || '';
                document.getElementById('edit_description').value = button.dataset.desc || '';
                document.getElementById('edit_product_id').value = button.dataset.id;
                document.getElementById('product_image').removeAttribute('required');
                document.getElementById('existing_image_url').value = button.dataset.img;

                // If you want to preview the image
                const imgPreview = document.getElementById('previewImage');
                if (imgPreview && button.dataset.img) {
                    imgPreview.src = button.dataset.img;
                    document.getElementById('imagePreview').style.display = 'block';
                    document.getElementById('uploadArea').style.display = 'none';
                }

                $('#edit_unit').val(button.dataset.unit).trigger('change');
            } else if (e.target.classList.contains('listing-btn-delete')) {
                if (confirm('Are you sure you want to delete this product?')) {
                    e.target.closest('.listing-card').remove();
                }
            } else if (e.target.classList.contains('listing-btn-toggle')) {
                const card = e.target.closest('.listing-card');
                const badge = card.querySelector('.listing-status-badge');
                const currentStatus = card.getAttribute('data-status');
                
                if (currentStatus === 'active') {
                    card.setAttribute('data-status', 'pending');
                    badge.textContent = 'Paused';
                    badge.className = 'listing-status-badge listing-status-pending';
                    e.target.textContent = 'Activate';
                } else {
                    card.setAttribute('data-status', 'active');
                    badge.textContent = 'Active';
                    badge.className = 'listing-status-badge listing-status-active';
                    e.target.textContent = 'Pause';
                }
            }
        });

        // Handle Edit Product Form Submission
        const editProductForm = document.getElementById('editProductForm');
        if (editProductForm) {
            editProductForm.addEventListener('submit', function (e) {
                e.preventDefault();

                const formData = new FormData(editProductForm);

                fetch('/farmer/listings/update-product-details', {
                    method: 'POST',
                    body: formData
                })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.message || "Something went wrong");
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    $('#editProductModal').modal('hide');
                    showFlashMessage(data.message || 'Product updated successfully!');
                    setTimeout(() => window.location.reload(), 1000);
                })
                .catch(err => {
                    console.error(err);
                    alert(err.message || 'Failed to update product.');
                });
            });
        }
    }



    // Listener for showing the account deletion form
    const deleteAccountBtn = document.getElementById('st-delete-account');
    const reasonForm = document.getElementById('st-delete-reason');

    if (deleteAccountBtn && reasonForm) {
        
        document.addEventListener('click', function(event) {
            if (!deleteAccountBtn.contains(event.target) && !reasonForm.contains(event.target)) {
                reasonForm.classList.remove('active');
                reasonForm.classList.add('hidden');
            } else {
                reasonForm.classList.remove('hidden');
                reasonForm.classList.add('active');
            }
        });
    }


    // Listener for updating farmers product listings
    document.getElementById('editProductForm')


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
});



// Toggle cart panel
function toggleCart() {
    const cartPanel = document.getElementById('cartPanel');
    cartPanel.classList.toggle('active');
}


// Store quantities for each product
let productQuantities = {};

// Combined function to open marketplace modal with product info and quantity tracking
function openProductModal(button) {
    // Fill modal with product info
    document.getElementById('mpProductName').textContent = button.dataset.name || '';
    document.getElementById('mpProductLocal').textContent = button.dataset.local || '';
    document.getElementById('mpProductDesc').textContent = button.dataset.desc || '';
    document.getElementById('mpProductPrice').textContent = button.dataset.price || '';
    document.getElementById('mpProductQty').textContent = button.dataset.qty || '';
    document.getElementById('mpProductUnit').textContent = button.dataset.unit || '';
    document.getElementById('mpProductImage').src = button.dataset.img || '';
    
    // Set the current product ID and restore its quantity
    const productId = button.dataset.id;
    window.currentProductId = productId;
    const savedQuantity = productQuantities[productId] || 1;
    document.getElementById('mpQtyInput').value = savedQuantity;

    const productName = button.dataset.name || 'product';
    const slug = encodeURIComponent(productName.toLowerCase().replace(/\s+/g, '-'));
    const params = new URLSearchParams(window.location.search);
    params.set('product', slug);
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    history.pushState(null, '', newUrl);

    // Show the modal
    document.getElementById('productModal').classList.add('mp-active');
    document.body.style.overflow = 'hidden';
    document.body.style.overflowX = 'hidden';
    document.body.style.width = '100%';
}

// Close modal function - save quantity before closing
function closeProductModal() {
    // Save current quantity before closing
    if (window.currentProductId) {
        const currentQuantity = parseInt(document.getElementById('mpQtyInput').value) || 1;
        productQuantities[window.currentProductId] = currentQuantity;
    }

    const params = new URLSearchParams(window.location.search);
    params.delete('product');
    const newUrl = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}`;
    history.pushState(null, '', newUrl);

    // Close modal
    document.getElementById('productModal').classList.remove('mp-active');
    document.body.style.overflow = 'auto';
    document.body.style.width = '';
}

// ESC key to close the modal
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        closeProductModal();
    }
});


// Close modal when clicking outside the modal box
window.addEventListener('click', function (e) {
    const modal = document.getElementById('productModal');
    if (e.target === modal) {
        closeProductModal();
    }
});


window.addEventListener('DOMContentLoaded', () => {
    try {
        const params = new URLSearchParams(window.location.search);
        const slug = params.get('product');
        if (!slug) return;

        const buttons = document.querySelectorAll('.view-details-btn');
        for (let btn of buttons) {
            const name = btn.dataset.name || '';
            const btnSlug = name.toLowerCase().replace(/\s+/g, '-');
            if (btnSlug === slug) {
                openProductModal(btn);
                break;
            }
        }
    } catch (err) {
        console.error('Error auto-opening product modal:', err);
    }
});

function updateQty(change) {
    const input = document.getElementById('mpQtyInput');
    const currentValue = parseInt(input.value) || 1;
    const productQty = parseInt(document.getElementById('mpProductQty').textContent);
    const newValue = Math.max(1, currentValue + change);

    if (newValue <= productQty) {
        input.value = newValue;

        if (window.currentProductId) {
            productQuantities[window.currentProductId] = newValue;
        }
    } else {
        alert('No more stock available');
    }
}



