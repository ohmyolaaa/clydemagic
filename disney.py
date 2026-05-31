import requests
import json
import uuid
from fake_useragent import UserAgent

session = requests.Session()

ua = UserAgent()
request_id = str(uuid.uuid4())
em = input('email : ')
pa = input('pass : ')
url = "https://disney.api.edge.bamgrid.com/graph/v1/device/graphql"

headers = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.9",
    "authorization": "Bearer ZGlzbmV5JmJyb3dzZXImMS4wLjA.Cu56AgSfBTDag5NiRA81oLHkDZfu5L3CKadnefEAY84",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Host": "disney.api.edge.bamgrid.com",
    "Origin": "https://www.disneyplus.com",
    "Referer": "https://www.disneyplus.com/",
    "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "User-Agent": ua.random,
    "x-application-version": "d2adb22e",
    "x-bamsdk-client-id": "disney-svod-3d9324fc",
    "x-bamsdk-platform": "javascript/windows}/chrome",
    "X-BAMSDK-Platform-Id": "browser",
    "x-bamsdk-version": "d2adb22e-dplus-mlp",
    "x-bamtech-wpnx-mlp-identifier": "/",
    "x-bamtech-wpnx-mlp-locale": "en-us"
}

payload = {
    "query": "mutation registerDevice($input: RegisterDeviceInput!) { registerDevice(registerDevice: $input) { grant { grantType assertion } } }",
    "variables": {
        "input": {
            "deviceFamily": "browser",
            "applicationRuntime": "chrome",
            "deviceProfile": "windows",
            "deviceLanguage": "en-IT",
            "attributes": {
                "osDeviceIds": [],
                "manufacturer": "microsoft",
                "model": None,
                "operatingSystem": "windows",
                "operatingSystemVersion": "10.0",
                "browserName": "chrome",
                "browserVersion": "127.0.6533.120"
            }
        }
    }
}

response = session.post(url, json=payload, headers=headers)

data = response.json()
token = data["extensions"]["sdk"]["token"]["accessToken"]

url = "https://disney.api.edge.bamgrid.com/v1/public/graphql"

headers = {
    "Host": "disney.api.edge.bamgrid.com",
    "accept": "application/json",
    "authorization": token,
    "content-type": "application/json",
    "x-bamsdk-platform-id": "android",
    "x-application-version": "4.0.1-rc1-2025.01.27.0",
    "x-bamsdk-client-id": "disney-svod-3d9324fc",
    "x-bamsdk-platform": "android/google/handset",
    "x-bamsdk-version": "9.20.0",
    "x-dss-edge-accept": "vnd.dss.edge+json; version=2",
    "x-request-id": request_id,
    "x-bamsdk-location-sharing-status": "WITHHELD",
    "user-agent": ua.random,
    "accept-encoding": "gzip"
}

payload = {
    "operationName": "check",
    "variables": {"email": em},
    "query": "query check($email: String!) { check(email: $email) { operations nextOperation } }"
}

response = session.post(url, json=payload, headers=headers)

url = "https://disney.api.edge.bamgrid.com/v1/public/graphql"

headers = {
    "User-Agent": ua.random,
    "Pragma": "no-cache",
    "Accept": "*/*",
    "Host": "disney.api.edge.bamgrid.com",
    "authorization": token,
    "content-type": "application/json",
    "x-bamsdk-platform-id": "android",
    "x-application-version": "4.0.1-rc1-2025.01.27.0",
    "x-bamsdk-client-id": "disney-svod-3d9324fc",
    "x-bamsdk-platform": "android/google/handset",
    "x-bamsdk-version": "9.20.0",
    "x-dss-edge-accept": "vnd.dss.edge+json; version=2",
    "x-request-id": request_id,
    "x-bamsdk-location-sharing-status": "WITHHELD",
    "content-length": "3213",
    "accept-encoding": "gzip"
}

payload = {
    "query": "    mutation login($input: LoginInput!) {        login(login: $input) {            account {                ...account                profiles {                    ...profile                }            }            actionGrant            activeSession {              ...session            }            identity {              ...identity          }        }    }    fragment identity on Identity {    attributes {        securityFlagged        createdAt        passwordResetRequired    }    flows {        marketingPreferences {            eligibleForOnboarding            isOnboarded        }        personalInfo {            eligibleForCollection            requiresCollection        }    }    personalInfo {        dateOfBirth        gender    }    subscriber {        subscriberStatus        subscriptionAtRisk        overlappingSubscription        doubleBilled        doubleBilledProviders        subscriptions {            id            groupId            state            partner            isEntitled            source {                sourceType                sourceProvider                sourceRef                subType            }            paymentProvider            product {                id                sku                offerId                promotionId                name                nextPhase {                    sku                    offerId                    campaignCode                    voucherCode                }                entitlements {                    id                    name                    desc                    partner                }                categoryCodes                redeemed {                    campaignCode                    redemptionCode                    voucherCode                }                bundle                bundleType                subscriptionPeriod                earlyAccess                trial {                    duration                }            }            term {                purchaseDate                startDate                expiryDate                nextRenewalDate                pausedDate                churnedDate                isFreeTrial            }            externalSubscriptionId,            cancellation {                type                restartEligible            }            stacking {                status                overlappingSubscriptionProviders                previouslyStacked                previouslyStackedByProvider            }        }    }}    fragment account on Account {    id    attributes {        blocks {            expiry            reason        }        consentPreferences {            dataElements {                name                value            }            purposes {                consentDate                firstTransactionDate                id                lastTransactionCollectionPointId                lastTransactionCollectionPointVersion                lastTransactionDate                name                status                totalTransactionCount                version            }        }        dssIdentityCreatedAt        email        emailVerified        lastSecurityFlaggedAt        locations {            manual {                country            }            purchase {                country                source            }            registration {                geoIp {                    country                }            }        }        securityFlagged        tags        taxId        userVerified    }    parentalControls {        isProfileCreationProtected    }    flows {        star {            isOnboarded        }    }}    fragment profile on Profile {    id    name    isAge21Verified    attributes {        avatar {            id            userSelected        }        isDefault        kidsModeEnabled        languagePreferences {            appLanguage            playbackLanguage            preferAudioDescription            preferSDH            subtitleAppearance {                backgroundColor                backgroundOpacity                description                font                size                textColor            }            subtitleLanguage            subtitlesEnabled        }        groupWatch {            enabled        }        parentalControls {            kidProofExitEnabled            isPinProtected        }        playbackSettings {            autoplay            backgroundVideo            prefer133            preferImaxEnhancedVersion            previewAudioOnHome            previewVideoOnHome        }    }    personalInfo {        dateOfBirth        gender        age    }    maturityRating {        ...maturityRating    }    personalInfo {        dateOfBirth        age        gender    }    flows {        personalInfo {            eligibleForCollection            requiresCollection        }        star {            eligibleForOnboarding            isOnboarded        }    }}fragment maturityRating on MaturityRating {    ratingSystem    ratingSystemValues    contentMaturityRating    maxRatingSystemValue    isMaxContentMaturityRating}    fragment session on Session {    device {        id        platform    }    entitlements    features {        coPlay    }    inSupportedLocation    isSubscriber    location {        type        countryCode        dma        asn        regionName        connectionType        zipCode    }    sessionId    experiments {        featureId        variantId        version    }    identity {        id    }    account {        id    }    profile {        id        parentalControls {            liveAndUnratedContent {                enabled            }        }    }    partnerName    preferredMaturityRating {        impliedMaturityRating        ratingSystem    }    homeLocation {        countryCode    }    portabilityLocation {        countryCode        type    }}",
    "operationName": "login",
    "variables": {
        "input": {
            "email": em,
            "password": pa
        }
    }
}

response = session.post(url, json=payload, headers=headers)
print(response.text)

login = response.json()
access_token = login["extensions"]["sdk"]["token"]["accessToken"]
print(access_token)

url = "https://disney.api.edge.bamgrid.com/v2/subscribers"

headers = {
    "Host": "disney.api.edge.bamgrid.com",
    "Connection": "keep-alive",
    "authority": "disney.api.edge.bamgrid.com",
    "accept": "application/json; charset=utf-8",
    "accept-language": "en-US,en;q=0.9,hi;q=0.8",
    "authorization": f"Bearer {access_token}",
    "content-type": "application/json; charset=utf-8",
    "origin": "https://www.disneyplus.com",
    "referer": "https://www.disneyplus.com/",
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": ua.random,
    "x-application-version": "1.1.2",
    "x-bamsdk-client-id": "disney-svod-3d9324fc",
    "x-bamsdk-platform": "windows",
    "x-bamsdk-version": "12.0",
    "x-dss-edge-accept": "vnd.dss.edge+json; version=2",
    "Accept-Encoding": "gzip, deflate"
}

response = session.get(url, headers=headers)
print(response.text)