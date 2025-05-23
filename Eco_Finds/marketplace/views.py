from django.contrib.admin.templatetags.admin_modify import submit_row
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.hashers import make_password, check_password
from .models import Product, CartItem, Category, Reward
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Order, CardDetails, Checkout, UserHistory
from .forms import UserRegistrationForm, CheckoutForm, CardDetailsForm, RewardForm
from .forms import ForgetPasswordForm, SetNewPasswordForm
from .models import UserRegistration
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile
from django.http import JsonResponse
from datetime import datetime, timedelta
import json
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from decimal import Decimal
from django.http import HttpResponse
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from django.db import transaction
from decimal import InvalidOperation

def home(request):
    products = Product.objects.all()
    bamboo_category = Category.objects.get(name="Bamboo_Products")
    bamboo_products = Product.objects.filter(category=bamboo_category)[:5]

    home_essentials_category = Category.objects.get(name="Home_Essentials")
    kids_section_category = Category.objects.get(name="Kids_Section")
    men_clothing_category = Category.objects.get(name="Men_Clothing")
    women_clothing_category = Category.objects.get(name="Women_Clothing")
    recycled_category = Category.objects.get(name="Recycled_Products")

    home_essentials = Product.objects.filter(category=home_essentials_category)
    kids_section = Product.objects.filter(category=kids_section_category)
    men_clothing = Product.objects.filter(category=men_clothing_category)
    women_clothing = Product.objects.filter(category=women_clothing_category)
    recycled_products = Product.objects.filter(category=recycled_category)

    username = request.session.get('username', None)

    context = {
        'products': products,
        'bamboo_products': bamboo_products,
        'home_essentials': home_essentials,
        'kids_section': kids_section,
        'recycled_products': recycled_products,
        'men_clothing': men_clothing,
        'women_clothing': women_clothing,
        'username': username,
    }

    return render(request, 'marketplace/home.html', context)

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                request.session['username'] = username
                request.session.set_expiry(300)  # Set session to expire in 5 minutes
                request.session['last_touch'] = timezone.now().timestamp()
                messages.info(request, f'You are now logged in as {username}.')
                return redirect('home')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})



def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    reviews = product.reviews.all()
    if request.method == 'POST':
        review_form = ReviewForm(request.POST)
        if review_form.is_valid():
            review = review_form.save(commit=False)
            review.user = request.user
            review.product = product
            review.save()
            return redirect('product_detail', product_id=product.id)
    else:
        review_form = ReviewForm()
    return render(request, 'marketplace/Products.html', {'product': product, 'reviews': reviews, 'review_form': review_form, 'username': request.session.get('username')})

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}!')
            return redirect('login')
        else:
            print(form.errors)  # For debugging purposes
    else:
        form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'Your session has expired. Please log in again.')
    return redirect('login')



def products(request):
    category_name = request.GET.get('category', None)
    if category_name:
        products = Product.objects.filter(category__name=category_name)
    else:
        products = Product.objects.all()

    categories = Category.objects.all()
    username = request.session.get('username', None)
    return render(request, 'marketplace/Products.html', {
        'products': products,
        'categories': categories,
        'username': username,
        'category_name': category_name
    })


@login_required
def checkout(request):
    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            checkout = form.save(commit=False)
            checkout.user = request.user
            checkout.save()
            cart_items = CartItem.objects.filter(user=request.user)
            cart_data = [{'product_id': item.product.id, 'name': item.product.name, 'quantity': item.quantity} for item in cart_items]
            expiration_date = (datetime.now() + timedelta(days=1)).strftime("%a, %d-%b-%Y %H:%M:%S GMT")
            response = redirect('card_details', card_type=checkout.payment_method)
            response.set_cookie('cart_data', json.dumps(cart_data), expires=expiration_date)
            response.set_cookie('checkout_id', checkout.id, expires=expiration_date)
            return response
    else:
        form = CheckoutForm()
    return render(request, 'marketplace/checkout.html', {'form': form})


def forget_password(request):
    if request.method == 'POST':
        form = ForgetPasswordForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            try:
                user_registration = UserRegistration.objects.get(user__username=username)
                request.session['username'] = username
                request.session['security_question1'] = user_registration.security_question1
                request.session['security_question2'] = user_registration.security_question2
                return redirect('security_questions')
            except UserRegistration.DoesNotExist:
                messages.error(request, "Username does not exist.")
    else:
        form = ForgetPasswordForm()
    return render(request, 'registration/forget_password.html', {'form': form})


def security_questions(request):
    if request.method == 'POST':
        username = request.session.get('username')
        answer1 = request.POST.get('security_answer1')
        answer2 = request.POST.get('security_answer2')
        try:
            user_registration = UserRegistration.objects.get(user__username=username)
            if user_registration.security_answer1 == answer1 and user_registration.security_answer2 == answer2:
                return redirect('set_new_password')
            else:
                messages.error(request, "Security answers do not match our records.")
                return redirect('forget_password')
        except UserRegistration.DoesNotExist:
            messages.error(request, "User does not exist.")
            return redirect('forget_password')
    else:
        security_questions = {
            'question1': request.session.get('security_question1'),
            'question2': request.session.get('security_question2')
        }
    return render(request, 'registration/security_questions.html', {'security_questions': security_questions})


def set_new_password(request):
    if request.method == 'POST':
        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            username = request.POST.get('username')
            new_password = form.cleaned_data['new_password']
            confirm_password = form.cleaned_data['confirm_password']

            if new_password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return render(request, 'registration/set_new_password.html', {'form': form, 'username': username})

            try:
                user_registration = UserRegistration.objects.get(user__username=username)
                user = user_registration.user
                user.set_password(new_password)  # Use set_password method to hash the password
                user.save()
                messages.success(request, "Password reset successful. Please log in with your new password.")
                return redirect('login')
            except UserRegistration.DoesNotExist:
                messages.error(request, "User does not exist.")
                return redirect('forget_password')
    else:
        form = SetNewPasswordForm()
        username = request.session.get('username')
    return render(request, 'registration/set_new_password.html', {'form': form, 'username': username})


@login_required
def card_details_view(request, card_type):
    if request.method == 'POST':
        form = CardDetailsForm(request.POST)
        if form.is_valid():
            card_details = form.save(commit=False)
            card_details.checkout = Checkout.objects.create(user=request.user, payment_method=card_type)
            card_details.save()
            submit_payment(request)
            return redirect('order_success')
    else:
        form = CardDetailsForm(initial={'card_type': card_type})
    return render(request, 'marketplace/card_details.html', {'form': form})


@login_required
def submit_payment(request):
    if request.method == 'POST':
        user = request.user
        cart_items = CartItem.objects.filter(user=user)
        print(cart_items)
        # Get checkout details from the cookie
        checkout_id = request.COOKIES.get('checkout_id')
        if not checkout_id:
            return redirect('checkout')  # Redirect to checkout if no details found

        checkout = Checkout.objects.get(id=checkout_id)
        print(checkout.id)

        # Save order with checkout details
        order = Order.objects.create(
            user=user,
            shipping_address=f"{checkout.shipping_unit_no}, {checkout.shipping_street}, {checkout.shipping_city}, {checkout.shipping_pin}",
            billing_address= "418 Askin",
            product_name="default name",
        )
        order.items.set(cart_items)  # ensure this is set correctly
        order.save()

        # Calculate total reward points
        total_reward_points = float(sum(item.computed_reward_points for item in cart_items))
        for item in cart_items:
            print(item.computed_reward_points)
        print(total_reward_points)
        # Update user's reward points
        user_registration = UserRegistration.objects.get(user=user)
        print(user_registration.reward_points)
        user_registration.reward_points += Decimal(total_reward_points)
        user_registration.save()

        # Reduce product quantities
        for item in cart_items:
            item.product.quantity -= item.quantity
            item.product.save()

        # Clear cart
        #  cart_items.delete()

        # Clear the cookies
        response = redirect('order_success')
        response.delete_cookie('cart_items')
        response.delete_cookie('checkout_id')

        # Pass the total reward points to the order success view
        request.session['total_reward_points'] = total_reward_points




@login_required
def order_success(request):
    total_reward_points = request.session.pop('total_reward_points', 0)
    return render(request, 'marketplace/order_success.html', {
        'username': request.session.get('username'),
        'total_reward_points': total_reward_points
    })

def aboutus(request):
    return render(request, 'marketplace/aboutus.html')


@login_required
def rewards(request):
    user_registration = UserRegistration.objects.get(user=request.user)
    total_points = user_registration.reward_points
    points_value = total_points * 2

    rewards = Reward.objects.all()

    return render(request, 'marketplace/rewards.html', {
        'rewards': rewards,
        'total_points': total_points,
        'points_value': points_value,
    })



@login_required
def wishlist(request):
    user_registration = request.user.userregistration
    wishlist_items = user_registration.wishlist.all()
    return render(request, 'marketplace/partials/wishlist_items.html', {'wishlist_items': wishlist_items})



@login_required
def view_cart(request):
    cart_items = CartItem.objects.filter(user=request.user)
    total_price = sum(item.product.price * item.quantity for item in cart_items)
    total_reward_points = Decimal('0.00')
    tax = total_price * Decimal('0.08')  # Assuming 8% tax rate
    total_amount = total_price + tax

    user_registration = UserRegistration.objects.get(user=request.user)
    available_reward_points = user_registration.reward_points

    reward_points_applied = 0
    if request.method == 'POST' and 'redeem_points' in request.POST:
        reward_points_to_redeem = Decimal(request.POST.get('reward_points', '0'))
        if reward_points_to_redeem <= available_reward_points:
            discount = (reward_points_to_redeem // 10) * Decimal('1.5')
            total_amount -= discount
            reward_points_applied = reward_points_to_redeem
            # Update user's reward points
            user_registration.reward_points -= reward_points_to_redeem
            user_registration.save()
        else:
            messages.error(request, "You do not have enough reward points to redeem that amount.")

    total_amount = round(total_amount, 2)  # Round off total amount to 2 decimal points

    # Pre-compute reward points for each cart item
    cart_items = list(cart_items)  # Convert QuerySet to a list to modify the items
    for item in cart_items:
        try:
            product_price = Decimal(item.product.price)
            item_quantity = Decimal(item.quantity)
            item_reward_points = product_price * Decimal('0.7') * item_quantity  # Example calculation: 10% of product price
            total_reward_points += item_reward_points
            item.computed_reward_points = item_reward_points.quantize(Decimal('0.00'))
            print(item.computed_reward_points)
            item.save()
            # Save the reward points back to the product or cart item as needed
        except (InvalidOperation, ValueError) as e:
            print(f"Error calculating reward points for product {item.product.name}: {e}")
            item.computed_reward_points = Decimal('0.00')
            item.save()

    return render(request, 'marketplace/cart.html', {
        'cart_items': cart_items,
        'total_price': total_price,
        'total_reward_points': total_reward_points,
        'tax': tax,
        'total_amount': total_amount,
        'available_reward_points': available_reward_points,
        'reward_points_applied': reward_points_applied,
    })



@login_required
def add_to_cart(request, product_id):
    print(f"Adding product {product_id} to cart")
    product = get_object_or_404(Product, id=product_id)
    cart_item, created = CartItem.objects.get_or_create(user=request.user, product=product)
    if not created:
        cart_item.quantity += 1
        print(f"Incrementing quantity for product {product_id}")
        cart_item.save()
    else:
        cart_item.save()
        print(f"Added product {product_id} to cart")
    return redirect('view_cart')

@login_required
def remove_from_cart(request, product_id):
    try:
        cart_item = CartItem.objects.get(product_id=product_id, user=request.user)
       # cart_item.delete()
    except CartItem.DoesNotExist:
        pass

    return redirect('view_cart')

@login_required
def toggle_favorite(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product__id=product_id)
    cart_item.is_favorite = not cart_item.is_favorite
    cart_item.save()
    return redirect('view_cart')


@login_required
def update_quantity(request, product_id, action):
    cart_item = get_object_or_404(CartItem, user=request.user, product__id=product_id)
    if action == 'increase':
        cart_item.quantity += 1
    elif action == 'decrease' and cart_item.quantity > 1:
        cart_item.quantity -= 1
    cart_item.save()

    # Calculate new totals
    cart_items = CartItem.objects.filter(user=request.user)
    total_price = sum(item.total_price for item in cart_items)
    total_reward_points = sum(item.computed_reward_points for item in cart_items)
    tax = total_price * Decimal('0.1')  # Assuming a 10% tax rate
    total_amount = total_price + tax

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'new_quantity': cart_item.quantity,
            'new_total_price': float(cart_item.total_price),
            'new_reward_points': float(cart_item.computed_reward_points),
            'new_cart_total': float(total_price),
            'new_tax': float(tax),
            'new_total_amount': float(total_amount),
        })
    return redirect('view_cart')

@login_required
def apply_reward_points(request):
    if request.method == 'POST':
        points_to_redeem = int(request.POST.get('reward_points', 0))
        user_registration = request.user.userregistration

        if points_to_redeem <= user_registration.reward_points:
            user_registration.reward_points -= points_to_redeem
            user_registration.save()
            return JsonResponse({'success': True, 'available_reward_points': user_registration.reward_points})
        else:
            return JsonResponse({'success': False, 'error': 'Insufficient reward points'})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})




@login_required
def add_to_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    user_registration = request.user.userregistration
    user_registration.wishlist.add(product)
    return JsonResponse({'success': True})

@login_required
def remove_from_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    user_registration = request.user.userregistration
    user_registration.wishlist.remove(product)
    return redirect('home')

@login_required
def add_to_cart_from_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart_item, created = CartItem.objects.get_or_create(user=request.user, product=product)
    if not created:
        cart_item.quantity += 1
        cart_item.save()
    else:
        cart_item.save()


    user_registration = request.user.userregistration
    user_registration.wishlist.remove(product)

    return redirect('view_cart')  # Redirect to the cart page after adding the product



def cart_view(request):
    try:
        cart = Cart.objects.get(user=request.user)
        items = CartItem.objects.filter(cart=cart)
        total_price = sum(item.get_total_price() for item in items)
    except Cart.DoesNotExist:
        cart = None
        items = []
        total_price = 0

    context = {
        'cart': cart,
        'items': items,
        'total_price': total_price
    }
    return render(request, 'cart.html', context)


def product_showcase(request):
    categories = Category.objects.all()
    products = Product.objects.all()
    return render(request, 'marketplace/Products.html', {
        'categories': categories,
        'products': products
    })


@login_required
def profile(request):
    user_orders = Order.objects.filter(user=request.user)
    history, created = UserHistory.objects.get_or_create(user=request.user)

    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)
    user_registration, created = UserRegistration.objects.get_or_create(user=user)

    # Check session for visit tracking
    session_key = f'profile_visited_{user.id}'
    if not request.session.get(session_key, False):
        profile.visit_count += 1
        profile.last_visit = timezone.now()
        profile.save()
        request.session[session_key] = True

    # Fetch the latest shipping address
    latest_order = user_orders.order_by('-ordered_at').first()
    shipping_address = latest_order.shipping_address if latest_order else "No shipping address available."

    # Fetch the latest phone number from the Checkout table
    latest_checkout = Checkout.objects.filter(user=user).order_by('-id').first()
    phone_number = latest_checkout.phone if latest_checkout else "No phone number available."

    context = {
        'user_orders': user_orders,
        'last_login': user.last_login,
        'history': history,
        'username': request.session.get('username'),
        'user_registration': user_registration,
        'profile': profile,
        'shipping_address': shipping_address,
        'phone_number': phone_number,  # Add phone_number to the context
    }
    return render(request, 'marketplace/profile.html', context)



@login_required
def order_history(request):
    orders = Order.objects.filter(user=request.user).order_by('-id')
    print("hello")
    for order in orders:
        print(order.items)
        for item in order.items.all():
            print(item.id)
            print(f"Order: {order.id}, Item: {item.product.name}, Quantity: {item.quantity}, Price: {item.product.price}, Image URL: {item.product.image.url}")  # Detailed debug statement
    return render(request, 'marketplace/order_history.html', {'orders': orders})



@login_required
def item_details(request, item_id):
    item = get_object_or_404(CartItem, id=item_id)  # Ensure this is the correct model
    data = {
        'name': item.product.name,
        'description': item.product.description,
        'price': float(item.product.price),
        'quantity': item.quantity,
        'total_price': float(item.product.price * item.quantity),
        'image_url': item.product.image.url,
    }
    return JsonResponse(data)


@login_required
def generate_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # Create the HttpResponse object with the appropriate PDF headers.
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=order_{order_id}_invoice.pdf'

    # Create the PDF object, using the response object as its "file."
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='RightAlign', alignment=2))
    styles.add(ParagraphStyle(name='CenterAlign', alignment=1, fontSize=16, spaceAfter=20))

    # Header
    elements.append(Paragraph(f"Invoice #{order.id}", styles['Title']))
    elements.append(Paragraph(f"Order Date: {order.ordered_at.strftime('%B %d, %Y')}", styles['Normal']))
    elements.append(Paragraph(f"Ship to: {order.shipping_address}", styles['Normal']))
    elements.append(Spacer(1, 0.2 * inch))

    # Items
    elements.append(Paragraph("Items:", styles['Heading2']))

    data = [["Product", "Description", "Quantity", "Price", "Subtotal"]]
    for item in order.items.all():
        product_image_path = item.product.image.path
        img = Image(product_image_path, width=1 * inch, height=1 * inch)
        data.append([
            img,
            Paragraph(item.product.name, styles['Normal']),
            item.quantity,
            f"${item.product.price:.2f}",
            f"${item.total_price:.2f}"
        ])

    table = Table(data, colWidths=[1.5 * inch, 2.5 * inch, 1 * inch, 1 * inch, 1 * inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)

    # Total
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(f"Total: ${order.get_total_price():.2f}", styles['RightAlign']))

    # Build PDF
    doc.build(elements)
    return response



@login_required
def fetch_order_history(request):
    user_orders = Order.objects.filter(user=request.user).select_related('user').prefetch_related('items__product')
    orders = []
    for order in user_orders:
        items = []
        for item in order.items.all():
            items.append({
                'id': item.id,
                'name': item.product.name,
                'description': item.product.description,
                'price': float(item.product.price),
                'quantity': item.quantity,
                'subtotal': float(item.total_price),
                'image_url': item.product.image.url,
            })
        orders.append({
            'id': order.id,
            'ordered_at': order.ordered_at.strftime('%B %d, %Y'),
            'total_price': float(order.get_total_price()),
            'shipping_address': order.shipping_address,
            'items': items,
        })

    return JsonResponse({'orders': orders})