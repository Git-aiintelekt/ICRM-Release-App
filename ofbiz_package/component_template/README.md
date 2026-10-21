# iCRM Release Notes: OFBiz component

Package **@@FILE_NAME@@**. Latest version **@@VERSION@@**, generated @@GENERATED_AT@@ by @@GENERATED_BY@@.
It holds @@VERSION_COUNT@@ versions, @@ITEM_COUNT@@ changes and @@IMAGE_COUNT@@ screenshots.

This folder is a complete OFBiz component. It shows the iCRM release history (read-only) at
`/release-notes/control/main`. It needs nothing else at runtime: no Django, no FastAPI, no database of its own,
and no Java build (it has no Java code).

Don't edit these files by hand. Change the release notes in the Release Notes Django app, then use
**Generate OFBiz Package** there and deploy the new zip.

## First deployment

1. Unzip the package into `<ofbiz>/hot-deploy-ext/`, so that you have
   `<ofbiz>/hot-deploy-ext/release-notes/ofbiz-component.xml`.
2. Register the component: add this line inside `<component-loader>` in `<ofbiz>/hot-deploy-ext/component-load.xml`:

       <load-component component-location="release-notes"/>

3. Load the menu entry once, either:
   - in the browser: Web Tools → Import (`/webtools/control/EntityImport`), paste the contents of
     `data/ReleaseNotesSeedData.xml`, and click Import, or
   - from the command line: `ant load-file -Ddata-file=hot-deploy-ext/release-notes/data/ReleaseNotesSeedData.xml`
4. Restart OFBiz. `ant clean build` isn't needed for this component, but running it does no harm.
5. Open **Release Notes** in the iCRM app menu, or go to `https://<ofbiz-host>:<https-port>/release-notes/control/main`.

Full-access admins see the menu entry straight away. For everyone else, grant the `RELEASE_NOTES_VIEW`
permission to their security groups in iCRM Admin.

## Updating to a newer package

1. Delete `<ofbiz>/hot-deploy-ext/release-notes/` and unzip the new package in its place.
2. That's all. OFBiz reloads the page template within 10 seconds (`template.ftl.location.expireTime`) and serves
   the new static files straight away. Restart OFBiz if you prefer, or if the page still shows the old notes.

`package-manifest.json` lists the versions in this package and a SHA-256 checksum for every file.

## What's inside

    ofbiz-component.xml                      the component: two webapps and the menu data
    data/ReleaseNotesSeedData.xml            menu entry + RELEASE_NOTES_VIEW permission (load once)
    widget/CommonScreens.xml                 decorator for the shared iCRM sign-in screens
    webapp/release-notes/WEB-INF/            web.xml + controller.xml: /release-notes/control/main, sign-in required
    webapp/release-notes/main.ftl            the page, with every release embedded as JSON
    webapp/release-notes-resource/assets/    the React viewer (js, css)
    webapp/release-notes-resource/images/    screenshots
    package-manifest.json                    versions, counts, checksums
