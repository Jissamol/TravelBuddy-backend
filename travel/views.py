from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.core.cache import cache
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import TravelPlan, Itinerary, PlanItinerary
from .serializers import TravelPlanSerializer, ItinerarySerializer, PlanItinerarySerializer
import asyncio
import aiohttp
import urllib.parse
import os
import requests
from dotenv import load_dotenv
import json
import traceback
import hashlib
from math import radians, sin, cos, sqrt, asin
from datetime import datetime, timedelta

# Load .env for Google Places API key
base_dir = getattr(settings, "BASE_DIR", None)
if base_dir:
    load_dotenv(os.path.join(str(base_dir), ".env"))

GOOGLE_PLACES_API_BASE = "https://places.googleapis.com/v1/places:searchNearby"
GOOGLE_PLACES_PHOTO_BASE = "https://places.googleapis.com/v1"
GOOGLE_PLACES_DETAILS_BASE = "https://places.googleapis.com/v1/places"
GOOGLE_PLACES_TEXT_BASE = "https://places.googleapis.com/v1/places:searchText"
UNSPLASH_SEARCH_BASE = "https://api.unsplash.com/search/photos"
FALLBACK_PLACE_IMAGE = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='800' height='540' viewBox='0 0 800 540'>"
    "<rect width='800' height='540' fill='%23eef2f7'/>"
    "<rect x='60' y='60' width='680' height='420' rx='28' fill='%23f8fafc' stroke='%23e2e8f0'/>"
    "<circle cx='400' cy='220' r='70' fill='%23e2e8f0'/>"
    "<path d='M300 360h200' stroke='%2394a3b8' stroke-width='12' stroke-linecap='round'/>"
    "<path d='M260 400h280' stroke='%23cbd5e1' stroke-width='10' stroke-linecap='round'/>"
    "</svg>"
)
MAX_NEARBY_RESULTS = 20
PHOTO_LOOKUP_LIMIT = MAX_NEARBY_RESULTS
PHOTO_CACHE_TTL = 86400
TEXT_PHOTO_CACHE_TTL = 86400
DETAILS_QUOTA_CACHE_KEY = "places_details_quota_exhausted"
DETAILS_QUOTA_TTL = 3600
TEXT_QUOTA_CACHE_KEY = "places_text_quota_exhausted"
TEXT_QUOTA_TTL = 3600
UNSPLASH_CACHE_TTL = 86400
WIKIPEDIA_CACHE_TTL = 604800

# =====================================================
# Haversine formula
# =====================================================
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2*asin(sqrt(a))
    r = 6371  # Radius of Earth in km
    return c * r

def _get_google_api_key():
    return os.environ.get("GOOGLE_API_KEY", "").strip()

def _get_foursquare_api_key():
    return os.environ.get("FOURSQUARE_API_KEY", "").strip()

def _get_unsplash_access_key():
    return os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()

def _hashed_cache_key(prefix, raw_value):
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"

def _photo_proxy_url(request, photo_name, place_id):
    base_url = request.build_absolute_uri(reverse("nearby-place-photo"))
    if not photo_name:
        return f"{base_url}?fallback=1&place_id={urllib.parse.quote(place_id or 'unknown')}"
    return (
        f"{base_url}?photo_name={urllib.parse.quote(photo_name)}"
        f"&max_width=800&place_id={urllib.parse.quote(place_id or 'unknown')}"
    )

def _normalize_category(category):
    if not category:
        return "tourist_spots"
    return category.strip().lower().replace(" ", "_")

def _google_places_params(lat, lon, category, radius):
    category_map = {
        "tourist_spots": ["tourist_attraction"],
        "tourist": ["tourist_attraction"],
        "restaurants": ["restaurant"],
        "hotels": ["lodging"],
        "nature": ["park", "natural_feature"],
        "museums": ["museum"],
    }
    category_key = _normalize_category(category)
    return {
        "includedTypes": category_map.get(category_key, ["tourist_attraction"]),
        "maxResultCount": MAX_NEARBY_RESULTS,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(radius),
            }
        },
    }



def _fetch_unsplash_photo(name, address=None):
    access_key = _get_unsplash_access_key()
    if not access_key or not name:
        if settings.DEBUG:
            if not access_key:
                print("[Unsplash] missing access key")
            if not name:
                print("[Unsplash] missing place name")
        return None

    # Search Unsplash by place name only (ignoring address to avoid over-specification)
    query = name
    cache_key = _hashed_cache_key("unsplash_photo", query)
    cached = cache.get(cache_key)
    if cached is not None:
        if settings.DEBUG:
            print(f"[Unsplash] cache hit for {query}")
        return cached

    try:
        response = requests.get(
            UNSPLASH_SEARCH_BASE,
            params={
                "query": query,
                "per_page": 1,
                "orientation": "landscape",
            },
            headers={
                "Authorization": f"Client-ID {access_key}",
                "Accept-Version": "v1",
            },
            timeout=12,
        )
        if response.status_code != 200:
            if settings.DEBUG:
                print(
                    f"[Unsplash] {query} status={response.status_code} body={response.text[:300]}"
                )
            cache.set(cache_key, None, UNSPLASH_CACHE_TTL)
            return None
        try:
            payload = response.json() or {}
        except ValueError:
            if settings.DEBUG:
                print(f"[Unsplash] {query} invalid JSON response")
            cache.set(cache_key, None, UNSPLASH_CACHE_TTL)
            return None

        results = payload.get("results", [])
        if not results:
            if settings.DEBUG:
                print(f"[Unsplash] no results for {query}")
            cache.set(cache_key, None, UNSPLASH_CACHE_TTL)
            return None

        image_url = results[0].get("urls", {}).get("regular")
        if not image_url and settings.DEBUG:
            print(f"[Unsplash] missing image URL for {query}")
        cache.set(cache_key, image_url, UNSPLASH_CACHE_TTL)
        return image_url
    except requests.RequestException:
        return None

def _fetch_wikipedia_image(name):
    if not name:
        return None
    cache_key = _hashed_cache_key("wikipedia_image", name)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    headers = {
        "User-Agent": "TravelBuddyApp/1.0 (contact: admin@travelbuddy.com)"
    }

    try:
        # Step 1: Search Wikipedia using the query API to get the closest page title
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": name,
            "format": "json",
            "utf8": 1
        }
        
        search_resp = requests.get(search_url, headers=headers, params=search_params, timeout=8)
        if search_resp.status_code != 200:
            cache.set(cache_key, None, WIKIPEDIA_CACHE_TTL)
            return None
            
        search_data = search_resp.json()
        search_results = search_data.get("query", {}).get("search", [])
        if not search_results:
            cache.set(cache_key, None, WIKIPEDIA_CACHE_TTL)
            return None
            
        best_title = search_results[0].get("title")
        
        # Step 2: Fetch Page Summary (including its actual image)
        encoded_title = urllib.parse.quote(best_title.replace(" ", "_"))
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
        summary_resp = requests.get(summary_url, headers=headers, timeout=8)
        
        if summary_resp.status_code != 200:
            cache.set(cache_key, None, WIKIPEDIA_CACHE_TTL)
            return None
            
        summary_data = summary_resp.json()
        image_url = (
            summary_data.get("thumbnail", {}).get("source")
            or summary_data.get("originalimage", {}).get("source")
        )
        cache.set(cache_key, image_url, WIKIPEDIA_CACHE_TTL)
        return image_url
    except Exception:
        return None

def _fetch_fallback_image(name, address, category=None):
    # Prefer specific exact Wikipedia image first (real photo)
    wiki_img = _fetch_wikipedia_image(name)
    if wiki_img:
        return wiki_img

    # Fall back to Unsplash photo (fuzzy/curated search)
    unsplash_img = _fetch_unsplash_photo(name, None)
    if unsplash_img:
        return unsplash_img

    # If both failed, use highly curated, beautiful, rate-limit-free premium localized/tropical fallbacks
    category_key = _normalize_category(category)
    premium_fallbacks = {
        "tourist_spots": "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?auto=format&fit=crop&w=800&q=80",  # Kerala backwaters
        "tourist": "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?auto=format&fit=crop&w=800&q=80",
        "nature": "https://images.unsplash.com/photo-1482862549707-f63cb32c5fd9?auto=format&fit=crop&w=800&q=80",         # Lush tropical green forest waterfall
        "hotels": "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80",         # Luxury resort pool
        "restaurants": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80",    # Gourmet food
        "museums": "https://images.unsplash.com/photo-1579783900882-c0d3dad7b119?auto=format&fit=crop&w=800&q=80",        # Gallery art exhibition
    }
    
    fallback_url = premium_fallbacks.get(category_key, "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?auto=format&fit=crop&w=800&q=80")
    
    if settings.DEBUG:
        print(f"[FallbackImage] Specific match failed for '{name}'. Using premium static fallback: {fallback_url}")
        
    return fallback_url

# =====================================================
# UTILITY FUNCTIONS
# =====================================================
async def fetch_wikipedia(session, name):
    """Fetch Wikipedia summary and image for a place"""
    try:
        encoded_name = urllib.parse.quote(name.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_name}"
        async with session.get(url, timeout=8) as resp:
            if resp.status == 200:
                data = await resp.json()
                description = data.get("extract") or data.get("description")
                image = data.get("thumbnail", {}).get("source") or data.get("originalimage", {}).get("source")
                return {"description": description, "image": image}
    except (aiohttp.ClientError, asyncio.TimeoutError):
        pass
    return {"description": None, "image": None}

async def fetch_nominatim(session, lat, lon, semaphore):
    """Fetch location using Nominatim with caching and rate-limiting"""
    cache_key = f"loc_{round(lat,3)}_{round(lon,3)}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Bypass Nominatim live HTTP request to prevent rate-limits and severe timeouts
    return None

async def fetch_place_info(session, name, lat, lon, tags, nominatim_semaphore):
    """Fetch description, image, and location for a place"""
    description = "A beautiful tourist attraction worth visiting."
    image = None

    # Build location from OSM tags first
    location_parts = []
    for key in ["addr:suburb", "addr:district", "addr:city", "addr:town", "addr:village", "addr:state"]:
        val = tags.get(key)
        if val and val not in location_parts:
            location_parts.append(val)
        if len(location_parts) >= 2:
            break
    location = ", ".join(location_parts) if location_parts else None

    # Wikipedia fetch (parallel)
    wiki_task = asyncio.create_task(fetch_wikipedia(session, name))

    # Only call Nominatim if location not found from tags
    if not location and lat and lon:
        location = await fetch_nominatim(session, lat, lon, nominatim_semaphore)

    wiki_result = await wiki_task
    if wiki_result["description"]:
        description = wiki_result["description"]
        
    if wiki_result["image"]:
        image = wiki_result["image"]
    else:
        # Fall back to Unsplash photo
        try:
            loop = asyncio.get_running_loop()
            unsplash_image = await loop.run_in_executor(None, _fetch_unsplash_photo, name, None)
            if unsplash_image:
                image = unsplash_image
        except Exception:
            pass

    if not image:
        image = f"https://picsum.photos/seed/{urllib.parse.quote(name)}/400/300"

    return {"description": description, "image": image, "location": location or "Unknown"}

# =====================================================
# TRIP COLLABORATION & SHARING
# =====================================================

def get_trip_with_access(request, identifier, is_token=False):
    """Helper to check if user has access to a trip (owner, collaborator, or public)"""
    try:
        if is_token:
            plan = TravelPlan.objects.get(share_token=identifier)
        else:
            plan = TravelPlan.objects.get(id=identifier)
            
        if plan.is_public or plan.user is None:
            return plan, True
            
        if request.user.is_authenticated:
            if plan.user == request.user or plan.collaborators.filter(id=request.user.id).exists():
                return plan, True
                
        return None, False
    except TravelPlan.DoesNotExist:
        return None, False

@api_view(['GET'])
@permission_classes([AllowAny])
def get_trip_by_token(request, token):
    """Fetch trip details using a share token"""
    try:
        plan = TravelPlan.objects.get(share_token=token)
        # Even if not public, token access implies temporary view permission
        serializer = TravelPlanSerializer(plan, context={'request': request})
        return Response(serializer.data)
    except TravelPlan.DoesNotExist:
        return Response({"error": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_trip(request, token):
    """Add current user as a collaborator using a share token"""
    try:
        plan = TravelPlan.objects.get(share_token=token)
        if plan.user == request.user:
            return Response({"message": "You are the owner of this trip"}, status=status.HTTP_200_OK)
            
        plan.collaborators.add(request.user)
        return Response({"message": "Joined trip successfully", "id": plan.id}, status=status.HTTP_200_OK)
    except TravelPlan.DoesNotExist:
        return Response({"error": "Invalid share link"}, status=status.HTTP_404_NOT_FOUND)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_trip_visibility(request, plan_id):
    """Toggle public visibility of a trip (Owner only)"""
    try:
        plan = TravelPlan.objects.get(id=plan_id, user=request.user)
        plan.is_public = request.data.get('is_public', plan.is_public)
        plan.save()
        return Response({"is_public": plan.is_public})
    except TravelPlan.DoesNotExist:
        return Response({"error": "Trip not found or permission denied"}, status=status.HTTP_403_FORBIDDEN)

# =====================================================
# PERSONALIZED TRAVEL PLAN
# =====================================================
class PersonalizePlanView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TravelPlanSerializer(data=request.data)
        if serializer.is_valid():
            if request.user.is_authenticated:
                serializer.save(user=request.user)
            else:
                serializer.save(user=None)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# =====================================================
# DATABASE ITINERARIES
# =====================================================
@api_view(['GET'])
@permission_classes([AllowAny])
def top_itineraries(request):
    """Get all itineraries from database, optionally sorted by distance."""
    lat = request.query_params.get('lat')
    lon = request.query_params.get('lon')
    itineraries = Itinerary.objects.all()

    if lat and lon:
        try:
            lat = float(lat)
            lon = float(lon)
            for item in itineraries:
                item.distance = haversine(lat, lon, item.latitude, item.longitude)
            itineraries = sorted(itineraries, key=lambda x: x.distance)
        except ValueError:
            pass

    serializer = ItinerarySerializer(itineraries, many=True)
    return Response(serializer.data)

# =====================================================
# NEARBY TOURIST ATTRACTIONS
# =====================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def nearby_itineraries(request):
    """Sync wrapper around async nearby attractions with proper names and fallbacks."""

    try:
        lat = float(request.GET.get("lat"))
        lon = float(request.GET.get("lon"))
        radius = float(request.GET.get("radius", 20000))
    except (TypeError, ValueError):
        return Response({"error": "Invalid lat/lon"}, status=400)

    async def async_logic():
        query = f"""
        [out:json][timeout:25];
        (
          node["tourism"~"attraction|museum|monument|viewpoint|zoo|theme_park"](around:{int(radius)},{lat},{lon});
          node["historic"~"monument|castle|ruins|memorial"](around:{int(radius)},{lat},{lon});
        );
        out body;
        """

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    "https://overpass-api.de/api/interpreter", data=query, timeout=15
                ) as resp:
                    if resp.status != 200:
                        return {"error": "Failed to fetch nearby places"}
                    data = await resp.json()
            except Exception:
                return {"error": "Failed to fetch nearby places"}

            elements = data.get("elements", [])[:50]
            if not elements:
                return []

            semaphore = asyncio.Semaphore(1)
            tasks = []
            
            for el in elements:
                tags = el.get("tags", {})
                name = (
                    tags.get("name")
                    or tags.get("alt_name")
                    or tags.get("official_name")
                    or tags.get("int_name")
                    or tags.get("tourism")
                    or tags.get("historic")
                )

                if not name or name.lower() in ["viewpoint", "attraction", "monument", "museum"]:
                    continue

                tasks.append(fetch_place_info(
                    session,
                    name,
                    el.get("lat"),
                    el.get("lon"),
                    tags,
                    semaphore
                ))

            results = await asyncio.gather(*tasks)

            final_results = []
            for el, res in zip(elements, results):
                tags = el.get("tags", {})
                name = tags.get("name") or res.get("name") or "Scenic spot"
                if not el.get("lat") or not el.get("lon"):
                    continue

                dist = round(haversine(lat, lon, el["lat"], el["lon"]), 2)
                city = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village") or "Unknown"
                district = tags.get("addr:district") or tags.get("addr:suburb") or ""
                description = res.get("description") or f"A notable {tags.get('tourism', 'attraction').replace('_',' ')} near {city}."

                final_results.append({
                    "id": el.get("id"),
                    "name": name,
                    "description": description,
                    "lat": el["lat"],
                    "lon": el["lon"],
                    "city": city,
                    "district": district,
                    "location": res.get("location"),
                    "image": res.get("image"),
                    "distance": dist,
                })

            final_results.sort(key=lambda x: x["distance"])
            return final_results

    results = asyncio.run(async_logic())
    return Response(results)

# =====================================================
# GOOGLE PLACES - NEARBY PLACES
# =====================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def nearby_places(request):
    try:
        lat = float(request.query_params.get("lat"))
        lon = float(request.query_params.get("lon"))
    except (TypeError, ValueError):
        return Response({"error": "Invalid lat/lon"}, status=400)

    api_key = _get_google_api_key()
    if not api_key:
        return Response({"error": "Google Places API key is missing"}, status=500)

    category = request.query_params.get("category")
    try:
        radius = float(request.query_params.get("radius", 20000))
    except (TypeError, ValueError):
        radius = 20000

    radius = max(500, min(radius, 50000))
    payload = _google_places_params(lat, lon, category, radius)

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,places.location,"
            "places.rating,places.userRatingCount,"
            "places.photos.name,places.photos.widthPx,places.photos.heightPx"
        ),
    }

    try:
        response = requests.post(GOOGLE_PLACES_API_BASE, json=payload, headers=headers, timeout=12)
        if response.status_code == 429:
            if settings.DEBUG:
                print(
                    "[PlacesNearby] quota exhausted for searchNearby; returning empty results"
                )
            return Response([])
        if response.status_code != 200:
            return Response({
                "error": "Failed to fetch nearby places",
                "status_code": response.status_code,
            }, status=502)
        data = response.json()
    except requests.RequestException:
        return Response({"error": "Failed to fetch nearby places"}, status=502)

    places = data.get("places", [])
    if not places:
        return Response([])

    results = []
    seen_place_ids = set()
    for idx, place in enumerate(places):
        place_id = place.get("id")
        if not place_id or place_id in seen_place_ids:
            continue
        seen_place_ids.add(place_id)

        location = place.get("location", {})
        place_lat = location.get("latitude")
        place_lon = location.get("longitude")
        if place_lat is None or place_lon is None:
            continue

        display_name = (place.get("displayName") or {}).get("text")
        formatted_address = place.get("formattedAddress") or ""

        photos = place.get("photos") or []
        photo_name = photos[0].get("name") if photos else None
        image_url = None
        if photo_name:
            image_url = _photo_proxy_url(request, photo_name, place_id)
        else:
            image_url = _fetch_fallback_image(display_name or "", formatted_address, category)
            if not image_url:
                image_url = _photo_proxy_url(request, None, place_id)
        if settings.DEBUG:
            print(
                f"[Places] {display_name or place_id} | photo={photo_name or 'none'} | url={image_url}"
            )

        results.append({
            "place_id": place_id,
            "name": display_name or "Unknown place",
            "address": formatted_address,
            "rating": place.get("rating"),
            "user_ratings_total": place.get("userRatingCount", 0),
            "lat": place_lat,
            "lon": place_lon,
            "image": image_url,
            "distance": round(haversine(lat, lon, place_lat, place_lon), 2),
            "types": place.get("types", []),
        })

    results.sort(key=lambda x: ((x.get("rating") or 0), (x.get("user_ratings_total") or 0)), reverse=True)
    return Response(results[:MAX_NEARBY_RESULTS])

@api_view(["GET"])
@permission_classes([AllowAny])
def nearby_place_photo(request):
    api_key = _get_google_api_key()
    photo_name = request.query_params.get("photo_name")
    max_width = request.query_params.get("max_width", "800")
    fallback = request.query_params.get("fallback")

    if fallback or not api_key or not photo_name:
        return HttpResponse(FALLBACK_PLACE_IMAGE, content_type="image/svg+xml")

    try:
        media_url = f"{GOOGLE_PLACES_PHOTO_BASE}/{photo_name}/media"
        response = requests.get(
            media_url,
            params={"maxWidthPx": int(max_width)},
            headers={"X-Goog-Api-Key": api_key},
            timeout=12,
            allow_redirects=True,
        )
    except requests.RequestException:
        return HttpResponse(FALLBACK_PLACE_IMAGE, content_type="image/svg+xml")

    content_type = response.headers.get("Content-Type", "")
    if response.status_code != 200 or not content_type.startswith("image/"):
        return HttpResponse(FALLBACK_PLACE_IMAGE, content_type="image/svg+xml")

    return HttpResponse(response.content, content_type=content_type)

# =====================================================
# ROUTE ITINERARIES - PLACES ALONG THE ROUTE
# =====================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def route_itineraries(request):
    """Fetch tourist attractions along a route between start and destination."""
    try:
        start_lat = float(request.GET.get("start_lat"))
        start_lon = float(request.GET.get("start_lon"))
        dest_lat = float(request.GET.get("dest_lat"))
        dest_lon = float(request.GET.get("dest_lon"))
    except (TypeError, ValueError):
        return Response({"error": "Invalid coordinates"}, status=400)

    def point_to_line_distance(px, py, x1, y1, x2, y2):
        """Calculate perpendicular distance from point (px,py) to line segment (x1,y1)-(x2,y2)"""
        # Calculate distances (haversine expects degrees, converts internally)
        dist_start = haversine(x1, y1, px, py)
        dist_end = haversine(x2, y2, px, py)
        dist_line = haversine(x1, y1, x2, y2)
        
        if dist_line == 0:
            return dist_start
        
        # Use semi-perimeter formula (Heron's formula variant)
        s = (dist_start + dist_end + dist_line) / 2
        area_squared = s * (s - dist_start) * (s - dist_end) * (s - dist_line)
        
        if area_squared <= 0:
            return min(dist_start, dist_end)
        
        # Perpendicular distance = 2 * Area / Base
        perp_distance = (2 * sqrt(area_squared)) / dist_line
        return perp_distance

    async def async_logic():
        # Calculate route distance and search parameters
        route_distance = haversine(start_lat, start_lon, dest_lat, dest_lon)
        
        # Calculate midpoint for search
        mid_lat = (start_lat + dest_lat) / 2
        mid_lon = (start_lon + dest_lon) / 2
        
        # Maximum deviation from route line (in km) - much more lenient
        max_deviation = max(25, min(60, route_distance * 0.6)) 

        # Search radius: tightly bound around the route and deviation to prevent Overpass timeouts
        search_radius = (route_distance / 2 + max_deviation + 10) * 1000
        search_radius = min(100000, max(20000, search_radius))

        query = f"""
        [out:json][timeout:30];
        (
          nwr["tourism"~"attraction|museum|viewpoint|zoo|theme_park|artwork|gallery|information"](around:{int(search_radius)},{mid_lat},{mid_lon});
          nwr["historic"~"monument|castle|ruins|memorial|archaeological_site|heritage"](around:{int(search_radius)},{mid_lat},{mid_lon});
          nwr["natural"~"peak|waterfall|beach|cave|rock|wood"](around:{int(search_radius)},{mid_lat},{mid_lon});
          nwr["amenity"~"place_of_worship|park|library|theatre"](around:{int(search_radius)},{mid_lat},{mid_lon});
          nwr["leisure"~"park|garden|nature_reserve|water_park"](around:{int(search_radius)},{mid_lat},{mid_lon});
        );
        out center;
        """

        async with aiohttp.ClientSession() as session:
            try:
                headers = {"User-Agent": "TravelBuddyApp/1.0 (contact: admin@travelbuddy.com)"}
                async with session.post(
                    "https://overpass-api.de/api/interpreter", data=query, headers=headers, timeout=35
                ) as resp:
                    if resp.status != 200:
                        return {"error": f"Failed to fetch places, status={resp.status}"}
                    data = await resp.json()
            except Exception as e:
                return {"error": f"Failed to fetch places: {str(e)}"}

            elements = data.get("elements", [])
            if not elements:
                return {"itineraries": []}

            semaphore = asyncio.Semaphore(1)
            
            # Filter places along the route first
            filtered_elements = []
            for el in elements:
                tags = el.get("tags", {})
                place_lat = el.get("lat") or (el.get("center", {}).get("lat") if el.get("center") else None)
                place_lon = el.get("lon") or (el.get("center", {}).get("lon") if el.get("center") else None)
                
                if not place_lat or not place_lon:
                    continue
                
                # Store them back for later use
                el['lat'] = place_lat
                el['lon'] = place_lon

                # Get name
                name = (
                    tags.get("name")
                    or tags.get("alt_name")
                    or tags.get("official_name")
                )

                # Skip unnamed or generic places
                if not name or name.lower() in ["viewpoint", "attraction", "monument", "museum", "scenic spot"]:
                    continue

                # Calculate perpendicular distance from route line
                perp_dist = point_to_line_distance(
                    place_lat, place_lon,
                    start_lat, start_lon,
                    dest_lat, dest_lon
                )
                
                # Only include if close to the route
                if perp_dist <= max_deviation:
                    # Calculate distance from start
                    dist_from_start = haversine(start_lat, start_lon, place_lat, place_lon)
                    dist_from_end = haversine(dest_lat, dest_lon, place_lat, place_lon)
                    
                    # Place should be within the route bounds (with more tolerance)
                    if dist_from_start <= route_distance + 40 and dist_from_end <= route_distance + 40:
                        el['distance_from_start'] = dist_from_start
                        el['perp_distance'] = perp_dist
                        filtered_elements.append(el)

            # Sort by distance from start
            filtered_elements.sort(key=lambda x: x['distance_from_start'])
            
            # Limit to reasonable number of places to keep reverse geocoding fast
            filtered_elements = filtered_elements[:30]

            if not filtered_elements:
                return {"itineraries": []}

            # Fetch detailed info for filtered places
            tasks = []
            for el in filtered_elements:
                tags = el.get("tags", {})
                name = tags.get("name") or tags.get("alt_name") or "Tourist Spot"
                
                tasks.append(fetch_place_info(
                    session,
                    name,
                    el["lat"],
                    el["lon"],
                    tags,
                    semaphore
                ))

            results = await asyncio.gather(*tasks)

            # Build final results
            final_results = []
            for el, res in zip(filtered_elements, results):
                if not res:
                    continue
                    
                tags = el.get("tags", {})
                name = tags.get("name") or "Tourist Spot"
                
                city = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village") or "Unknown"
                district = tags.get("addr:district") or tags.get("addr:suburb") or ""
                
                category = tags.get("tourism") or tags.get("historic") or tags.get("natural") or "attraction"
                description = res.get("description") or f"A notable {category.replace('_', ' ')} worth visiting on your journey."

                final_results.append({
                    "id": el.get("id"),
                    "name": name,
                    "description": description,
                    "lat": el["lat"],
                    "lon": el["lon"],
                    "city": city,
                    "district": district,
                    "location": res.get("location"),
                    "image": res.get("image"),
                    "distance": round(el['distance_from_start'], 2),
                    "category": category,
                    "deviation": round(el['perp_distance'], 2)
                })

            return {"itineraries": final_results}

    result = asyncio.run(async_logic())
    
    if "error" in result:
        return Response(result, status=500)

    return Response(result)
    
    return Response(result)

# =====================================================
# SAVE PLAN ITINERARIES
# =====================================================
@api_view(['POST'])
@permission_classes([AllowAny])
def save_plan_itineraries(request):
    """Save itineraries for a travel plan after they've been fetched"""
    try:
        data = request.data
        plan_id = data.get('plan_id')
        start_location = data.get('start_location')
        destination = data.get('destination')
        itineraries = data.get('itineraries', [])
        
        # Find or create travel plan
        travel_plan = None
        if plan_id:
            try:
                travel_plan = TravelPlan.objects.get(id=plan_id)
            except TravelPlan.DoesNotExist:
                pass
        
        if not travel_plan:
            # Create new plan (dates may be None)
            travel_plan = TravelPlan.objects.create(
                user=request.user if request.user.is_authenticated else None,
                start_location=start_location,
                destination=destination
            )
        
        # Clear existing itineraries for this plan
        PlanItinerary.objects.filter(travel_plan=travel_plan).delete()
        
        # Default to 3 days since dates are removed
        num_days = 3
        
        # Divide itineraries into days
        places_per_day = len(itineraries) // num_days if num_days > 0 else len(itineraries)
        if places_per_day == 0:
            places_per_day = 1
        
        # Save itineraries
        for idx, itin in enumerate(itineraries):
            day_number = (idx // places_per_day) + 1
            if day_number > num_days:
                day_number = num_days
            
            order_in_day = idx % places_per_day
            
            PlanItinerary.objects.create(
                travel_plan=travel_plan,
                name=itin.get('name', 'Unknown Place'),
                description=itin.get('description', ''),
                latitude=itin.get('lat', 0),
                longitude=itin.get('lon', 0),
                image_url=itin.get('image', ''),
                city=itin.get('city', ''),
                location=itin.get('location', ''),
                distance=itin.get('distance', 0),
                category=itin.get('category', ''),
                day_number=day_number,
                order_in_day=order_in_day
            )
        
        return Response({
            'message': 'Itineraries saved successfully',
            'plan_id': travel_plan.id,
            'total_places': len(itineraries),
            'days': num_days
        })
        
    except Exception as e:
        print(f"Error saving plan itineraries: {str(e)}")
        print(traceback.format_exc())
        return Response({
            'error': str(e),
            'message': 'Failed to save itineraries'
        }, status=500)

# =====================================================
# GET ALL ITINERARIES DAY-WISE
# =====================================================
@api_view(['GET'])
@permission_classes([AllowAny])
def all_itineraries_daywise(request):
    """Get travel plan itineraries organized by day. Supports filtering by plan_id"""
    try:
        plan_id = request.query_params.get('plan_id')
        share_token = request.query_params.get('token')
        
        if plan_id:
            plan, has_access = get_trip_with_access(request, plan_id)
            if not has_access:
                return Response({"error": "Access denied"}, status=403)
            travel_plans = [plan]
        elif share_token:
            plan, has_access = get_trip_with_access(request, share_token, is_token=True)
            if not has_access:
                return Response({"error": "Access denied"}, status=403)
            travel_plans = [plan]
        else:
            # For general list, only show public or user's own/collaborated trips
            if request.user.is_authenticated:
                from django.db.models import Q
                travel_plans = TravelPlan.objects.filter(
                    Q(user=request.user) | Q(collaborators=request.user) | Q(is_public=True)
                ).distinct().order_by('-created_at')
            else:
                travel_plans = TravelPlan.objects.filter(is_public=True).order_by('-created_at')

        if not travel_plans:
            return Response([])
        
        result = []
        for plan in travel_plans:
            # ... rest of the logic ...
            # Refactor: Ensure each plan's info is included correctly
            days = PlanItinerary.objects.filter(travel_plan=plan).values_list('day_number', flat=True).distinct().order_by('day_number')
            for day_num in days:
                places = PlanItinerary.objects.filter(travel_plan=plan, day_number=day_num).order_by('order_in_day')
                if not places.exists(): continue
                
                current_date_iso = None
                places_data = [{
                    'id': p.id, 'name': p.name, 'description': p.description,
                    'location': p.location or p.city or 'Unknown',
                    'image': p.image_url or f"https://picsum.photos/seed/{p.name}/400/300",
                    'lat': float(p.latitude), 'lon': float(p.longitude),
                    'distance': p.distance, 'category': p.category
                } for p in places]
                
                result.append({
                    'day': day_num, # Relative to trip
                    'date': current_date_iso,
                    'plan_id': plan.id,
                    'share_token': str(plan.share_token),
                    'is_public': plan.is_public,
                    'start_location': plan.start_location,
                    'destination': plan.destination,
                    'places': places_data,
                    'updated_at': plan.updated_at.isoformat()
                })
        return Response(result)
        
        print(f"Returning {len(result)} days across {travel_plans.count()} plans")
        return Response(result)
        
    except Exception as e:
        error_msg = str(e)
        stack_trace = traceback.format_exc()
        print(f"Error in all_itineraries_daywise: {error_msg}")
        print(f"Stack trace: {stack_trace}")
        
        return Response({
            'error': error_msg,
            'message': 'An error occurred while fetching itineraries'
        }, status=500)

# =====================================================
# SMART PACKING CHECKLIST
# =====================================================
@api_view(['POST'])
@permission_classes([AllowAny])
def generate_packing_checklist(request):
    """
    Generate a smart packing checklist based on destination weather.
    
    Expects: { dest_lat, dest_lon, destination, plan_id? }
    Returns: categorized packing list with weather-based suggestions.
    """
    from .models import PackingChecklist
    from .serializers import PackingChecklistSerializer
    from .packing_rules import generate_packing_list
    import os

    try:
        data = request.data
        dest_lat = data.get('dest_lat') or data.get('destLat')
        dest_lon = data.get('dest_lon') or data.get('destLon')
        destination = data.get('destination', 'Unknown')
        plan_id = data.get('plan_id') or data.get('planId')

        if not dest_lat or not dest_lon:
            return Response({"error": "Destination coordinates (dest_lat, dest_lon) are required."}, status=400)

        num_days = 3  # Default trip duration

        # --- Fetch weather from OpenWeatherMap ---
        api_key = os.environ.get('OPENWEATHER_API_KEY', '').strip()
        if not api_key:
            # Try from Django settings
            from django.conf import settings as django_settings
            api_key = getattr(django_settings, 'OPENWEATHER_API_KEY', '').strip()

        weather_summary = {
            "avg_temp": 25,
            "min_temp": 20,
            "max_temp": 30,
            "rain_chance": 0,
            "snow_chance": 0,
            "avg_humidity": 50,
            "max_wind_speed": 10,
            "conditions": ["Clear"],
            "description": "Weather data unavailable — using defaults",
            "destination": destination,
        }

        if api_key:
            try:
                import requests
                weather_url = f"https://api.openweathermap.org/data/2.5/forecast?lat={dest_lat}&lon={dest_lon}&appid={api_key}&units=metric"
                weather_resp = requests.get(weather_url, timeout=10)

                if weather_resp.status_code == 200:
                    weather_data = weather_resp.json()
                    forecasts = weather_data.get("list", [])

                    if forecasts:
                        temps = [f["main"]["temp"] for f in forecasts]
                        humidities = [f["main"]["humidity"] for f in forecasts]
                        wind_speeds = [f["wind"]["speed"] * 3.6 for f in forecasts]  # m/s → km/h
                        conditions_set = set()
                        rain_count = 0
                        snow_count = 0

                        for f in forecasts:
                            for w in f.get("weather", []):
                                main = w.get("main", "")
                                conditions_set.add(main)
                                if main.lower() in ["rain", "drizzle", "thunderstorm"]:
                                    rain_count += 1
                                if main.lower() == "snow":
                                    snow_count += 1

                        total = len(forecasts)
                        weather_summary = {
                            "avg_temp": round(sum(temps) / len(temps), 1),
                            "min_temp": round(min(temps), 1),
                            "max_temp": round(max(temps), 1),
                            "rain_chance": round((rain_count / total) * 100, 1) if total else 0,
                            "snow_chance": round((snow_count / total) * 100, 1) if total else 0,
                            "avg_humidity": round(sum(humidities) / len(humidities), 1),
                            "max_wind_speed": round(max(wind_speeds), 1),
                            "conditions": list(conditions_set),
                            "description": weather_data.get("city", {}).get("name", destination),
                            "destination": destination,
                        }
                else:
                    print(f"OpenWeather API error: {weather_resp.status_code} — {weather_resp.text}")
            except Exception as e:
                print(f"Error fetching weather: {e}")
                # Continue with default weather summary

        # --- Generate packing list from rules engine ---
        packing_result = generate_packing_list(weather_summary, num_days)

        # --- Save to database if plan_id is provided ---
        checklist_data = None
        if plan_id:
            try:
                travel_plan = TravelPlan.objects.get(id=plan_id)
                checklist, created = PackingChecklist.objects.update_or_create(
                    travel_plan=travel_plan,
                    defaults={
                        "items": packing_result["items"],
                        "weather_summary": weather_summary,
                    }
                )
                checklist_data = PackingChecklistSerializer(checklist).data
            except TravelPlan.DoesNotExist:
                print(f"TravelPlan {plan_id} not found — returning checklist without saving")

        return Response({
            "items": packing_result["items"],
            "categories": packing_result["categories"],
            "stats": packing_result["stats"],
            "weather_summary": weather_summary,
            "plan_id": plan_id,
            "num_days": num_days,
            "checklist": checklist_data,
        })

    except Exception as e:
        print(f"Error generating packing checklist: {e}")
        print(traceback.format_exc())
        return Response({"error": str(e)}, status=500)


@api_view(['PUT'])
@permission_classes([AllowAny])
def update_packing_checklist(request, plan_id):
    """
    Update the checked/unchecked state of packing items, or add custom items.
    
    Expects: { items: [...] }
    """
    from .models import PackingChecklist
    from .serializers import PackingChecklistSerializer

    try:
        travel_plan = TravelPlan.objects.get(id=plan_id)
    except TravelPlan.DoesNotExist:
        return Response({"error": f"Travel plan {plan_id} not found"}, status=404)

    try:
        checklist = PackingChecklist.objects.get(travel_plan=travel_plan)
    except PackingChecklist.DoesNotExist:
        return Response({"error": "No packing checklist found for this plan"}, status=404)

    items = request.data.get('items')
    if items is not None:
        checklist.items = items
        checklist.save()

    serializer = PackingChecklistSerializer(checklist)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_plan_itinerary(request, plan_id):
    """Manually add an itinerary item to a travel plan"""
    try:
        plan = TravelPlan.objects.get(id=plan_id)
        
        # Check permission (owner or collaborator)
        if plan.user != request.user and not plan.collaborators.filter(id=request.user.id).exists():
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data
        
        # Calculate next order in day
        day_number = data.get('day_number', 1)
        last_item = PlanItinerary.objects.filter(travel_plan=plan, day_number=day_number).order_by('-order_in_day').first()
        order_in_day = (last_item.order_in_day + 1) if last_item else 0
        
        # Create the item
        itinerary_item = PlanItinerary.objects.create(
            travel_plan=plan,
            name=data.get('activity', 'Unnamed Activity'),
            description=data.get('description', ''),
            location=data.get('location', ''),
            latitude=data.get('latitude', 0), # Optional if manual
            longitude=data.get('longitude', 0),
            day_number=day_number,
            order_in_day=order_in_day,
            start_time=data.get('start_time'),
            end_time=data.get('end_time')
        )
        
        serializer = PlanItinerarySerializer(itinerary_item)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except TravelPlan.DoesNotExist:
        return Response({"error": "Travel plan not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# =====================================================
# TRAVEL PLAN CRUD VIEWS
# =====================================================
class TravelPlanListView(generics.ListAPIView):
    serializer_class = TravelPlanSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return TravelPlan.objects.filter(user=self.request.user).order_by('-created_at')
        # Allow fetching all public plans or everything for anonymous users if desired
        return TravelPlan.objects.all().order_by('-created_at')

class TravelPlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TravelPlanSerializer
    queryset = TravelPlan.objects.all()
    permission_classes = [AllowAny] # Ideally we'd want IsAuthenticated or custom permission but since token sharing exists, let's keep it simple.