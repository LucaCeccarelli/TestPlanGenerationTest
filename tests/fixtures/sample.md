# Sample Device Interface Standard

## 1 Scope

This document specifies the behaviour of the sample device. It contains no requirements.

## 3 Terms and definitions

No special terms are used in this document.

## 5 Requirements

The following clauses define the requirements for the sample device.

## 5.1 Response time

The device shall respond to any request within 500 ms. The device may log the request.

## 5.2 Malformed requests

If the request is malformed or the session has expired, the device shall not process the request and should return an error code.

## 5.3 Terminology note

The word "device" means the unit under test. Nothing here is required.
