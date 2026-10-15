## Libib to Shopify Sync App 

i need to create a new and manual webapp that my client can use to do the Libib Sync. similar to the automation setup we run but i'm realizing he's going to need to be able to do it on his own.


the new flow would be: 

 IN LIBIB: 

1. client will upload rental items to libib, for now they'll just do this manually or with UPC lookup. let's make a note for ourselves to eventually get them setup with a csv sheet so they can do bulk uploads to libib. 
2. They'll Ensure that the Title, Image, Description, Format, Genre, and any extra tags are correct.
IN WEBAPP: 

3. they come to a webpage. the webpage should keep track of the last time the syncing process was run. they press a button that should automatically export the libib barcodes and content, and capture all the products uploaded since the last time it was successfully run. it should compare them to the shopify rental library to confirm that these new products are not in shopify yet. 
    3a. It should display a list of the titles that it found. in case there was an error in the export, or they are not seeing the correct products. we should have instructions for them to be able to do the exports from libib themselves, and a place for them to upload the content and barcode sheets. we then run the process again using the uploaded sheets instead 
5. They should review and then confirm the products that will be sync'd to shopify
6. we should display a list of the movies now, and it should show the various fields and attributes needed for shopify. they will be able to review and confirm these sections. the sections are:
    - Title
    - Description
    - Format (pulled from the tags)
    - Genre (pulled from the tags)
    - Any Additional Tags
6a. if the Format or Genre doesn't match the mappings, we should Flag it, and provide them the proper list of mappings. we should tell them they need to go back into Libib and make the edits there, and then start the process over. 
7. if everything looks good they confirm and go onto the next step
8. now we need to add the poster images for the shopify input. we will do the tmdb lookup to try and get the poster images for each movie. we should then display the list of movies with the poster. if the image was not found, we should leave it blank. on all movies, they'll have the ability to paste a link to a image so they can either edit or fill in the movie poster.
9. once all of this is confirmed and good, they'll hit a button to begin the sync. this will create shopify products with the proper fields, image, handle, and especially barcode. 
10. it will then show them a list of the successfully created shopify products, and highlight any errors with steps for what to fix before running again. it will then instruct them to go to the shopify products page and print and apply the new barcodes. 
IN SHOPIFY:
11. they'll print and apply all the barcodes